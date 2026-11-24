"""Offline substitutes only. No local gameplay or provider connection."""
import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import httpx
from fastapi.testclient import TestClient
from adapter.qwen_baseline.config import QwenSettings
from adapter.qwen_baseline.fastapi_app import create_app
from adapter.actionbridge.api import create_app as create_enhanced_app
from adapter.qwen_baseline.prompt import ORIGINAL_PROMPT_TEMPLATE
from adapter.qwen_baseline.retrieval import RetrievedFact
from adapter.tests.test_qwen_runtime import create_database
from phase2.evaluation.budget_guard import ACTIVE_ATTEMPT, Budget, BudgetTransport, Denied, install, specification
from phase2.evaluation.guarded_components import clients, chain, embeddings


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scopes = []
        self.paths = {}
        for condition in ("B", "A"):
            for case in ("G1", "M1", "M2", "G2") + (("CANCEL", "FOLLOWUP") if condition == "A" else ()):
                family = "M2_G2" if case in ("M2", "G2") else "cancel" if case in ("CANCEL","FOLLOWUP") else case
                db = self.root / (condition + "_" + family + ".db")
                if not db.exists():
                    create_database(db)
                    with closing(sqlite3.connect(db)) as c, c:
                        c.execute("INSERT INTO Conversations(player_name,npc_name,npc_response,timestamp) VALUES ('All','Guard','Seed greeting','2025-01-01')")
                self.paths[case,condition] = db
                self.scopes.append({"case":case,"condition":condition,"db":str(db)})
        auth = {"combined":{"embedding_max":10,"chat_max":10},"Stage_C_authorised":False,
                "Stage_A":{"embedding_max":8,"chat_max":8},
                "Stage_B":{"additional_embedding_max":2,"additional_chat_max":2}}
        for name, data in (("auth",auth),("audit",{"observed_embedding_client_paths":0,"observed_chat_client_paths":0}),
                           ("manifest",{"cases":self.scopes})):
            (self.root/(name+".json")).write_text(json.dumps(data))
        self.budget = Budget.initialise(self.root/"budget.sqlite3",self.root/"auth.json",
                                        self.root/"audit.json",self.root/"manifest.json")
        self.requests, self.fail_chat, self.fail_embedding = [], False, False
        self.chat_action = "none"
        self.provider, self.async_provider = clients(self.budget,httpx.MockTransport(self.handle))
        self.settings = QwenSettings(base_url="https://offline.invalid/v1",api_key="offline-fixture",chat_model="qwen3.7-flash")

    def tearDown(self):
        self.provider.close()
        asyncio.run(self.async_provider.aclose())
        gc.collect()  # Legacy fixture factory leaves sqlite connections for GC.
        self.temp.cleanup()

    def handle(self, request):
        self.requests.append((request.url.path,json.loads(request.content)))
        if request.url.path.endswith("/embeddings"):
            if self.fail_embedding:
                return httpx.Response(503,json={"error":{"message":"OFFLINE embedding failure","type":"fixture"}})
            return httpx.Response(200,json={"object":"list","model":"text-embedding-v4",
                "data":[{"object":"embedding","embedding":[.0]*1024,"index":0}],
                "usage":{"prompt_tokens":1,"total_tokens":1}})
        if self.fail_chat:
            return httpx.Response(503,json={"error":{"message":"OFFLINE injected failure","type":"fixture"}})
        return httpx.Response(200,json={"id":"offline","object":"chat.completion","created":0,
            "model":"qwen3.7-flash","choices":[{"index":0,"finish_reason":"stop",
                "message":{"role":"assistant","content":json.dumps({"action":self.chat_action,"response":"OFFLINE fixture."})}}],
            "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}})

    def query(self, case="G1", condition="B"):
        s = specification(case,condition)
        return {"player_name":"PhaseIIPlayer","npc_name":s["npc"],"held_items":s["held"],"player_input":s["text"]}

    def app(self, case="G1", condition="B"):
        emb = embeddings(self.settings,self.provider,self.async_provider)
        class Retriever:
            def similarity_search(_, query, *, k):
                emb.embed_query(query)
                return [RetrievedFact("OFFLINE fixture fact")]
        factory = create_enhanced_app if condition=="A" else create_app
        app = factory(db_path=self.paths[case,condition],
                         chain=chain(self.settings,self.provider,self.async_provider),vector_store=Retriever())
        install(app,self.budget,case,condition,self.paths[case,condition])
        return app

    def test_headerless_valid_request_uses_two_guarded_dispatches_and_original_payload(self):
        from openai import DefaultHttpxClient
        with DefaultHttpxClient() as original:
            self.assertEqual(self.provider.timeout.as_dict(),original.timeout.as_dict())
            self.assertEqual(self.provider.follow_redirects,original.follow_redirects)
        with TestClient(self.app()) as client:
            result = client.post("/get_response",content=json.dumps(self.query()))
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(self.requests),2)
        body = self.requests[1][1]
        self.assertFalse(body["enable_thinking"])
        self.assertEqual(body.get("max_completion_tokens",body.get("max_tokens")),1024)
        self.assertEqual(body["temperature"],.6)
        expected = dict(player_name="PhaseIIPlayer",npc_name="Guard",personality="Harsh guard",
                        allowed_actions="open_door",world_facts="OFFLINE fixture fact",chat_history="",
                        held_items="0 Gold",player_input="I want to enter the dojo.")
        self.assertEqual(body["messages"][0]["content"],ORIGINAL_PROMPT_TEMPLATE.format(**expected))
        self.assertEqual(body["response_format"],{"type":"json_object"})
        self.assertEqual(self.requests[0][1]["model"],"text-embedding-v4")
        self.assertEqual(self.requests[0][1]["dimensions"],1024)
        self.assertEqual(self.budget.status()["transport_reserved_per_kind"],{"embedding":1,"chat":1})

    def test_free_routes_wrong_input_and_wrong_db_do_not_contact_provider(self):
        with TestClient(self.app()) as client:
            self.assertEqual(client.get("/").status_code,200)
            self.assertEqual(client.post("/get_latest_response",json=self.query()).status_code,200)
            query = self.query(); query["player_input"]="What?"
            self.assertEqual(client.post("/get_response",json=query).status_code,403)
        with self.assertRaises(Denied):
            self.budget.validate("G1","B",self.paths["M1","B"])
        self.assertEqual(self.requests,[])
        self.assertEqual(len(self.budget.status()["admitted_cases"]),0)
        with closing(self.budget.connect()) as db:
            recorded=json.loads(db.execute("SELECT reason FROM denials").fetchone()[0])
        self.assertEqual(recorded["request"]["player_input"],"What?")
        self.assertEqual(recorded["http_status"],403)

    def test_duplicate_and_restart_cannot_generate_again(self):
        with TestClient(self.app()) as client:
            self.assertEqual(client.post("/get_response",json=self.query()).status_code,200)
            self.assertGreaterEqual(client.post("/get_response",json=self.query()).status_code,400)
        self.budget = Budget(self.root/"budget.sqlite3")
        with TestClient(self.app()) as client:
            self.assertGreaterEqual(client.post("/get_response",json=self.query()).status_code,400)
        self.assertEqual(len(self.requests),2)

    def test_provider_failure_is_retained_without_sdk_or_manual_retry(self):
        self.fail_chat = True
        with TestClient(self.app()) as client:
            self.assertEqual(client.post("/get_response",json=self.query()).status_code,500)
            self.assertGreaterEqual(client.post("/get_response",json=self.query()).status_code,400)
        self.assertEqual(len(self.requests),2)
        status = Budget(self.root/"budget.sqlite3").status()
        self.assertEqual(status["admitted_cases"][0]["finished_http"],500)
        self.assertEqual(status["transport_dispatch_reservations"][-1]["http_status"],503)

    def test_missing_request_context_and_async_route_fail_closed(self):
        with self.assertRaises(Denied):
            self.provider.post("https://offline.invalid/v1/embeddings",json={})
        async def attempt():
            with self.assertRaises(Denied):
                await self.async_provider.post("https://offline.invalid/v1/embeddings",json={})
        asyncio.run(attempt())
        self.assertEqual(self.requests,[])

    def test_embedding_failure_does_not_spend_chat_or_permit_case_retry(self):
        self.fail_embedding = True
        with TestClient(self.app()) as client:
            self.assertEqual(client.post("/get_response",json=self.query()).status_code,500)
            self.assertGreaterEqual(client.post("/get_response",json=self.query()).status_code,400)
        status = self.budget.status()
        self.assertEqual(len(self.requests),1)
        self.assertEqual(status["transport_reserved_per_kind"],{"embedding":1,"chat":0})
        self.assertEqual(status["remaining_transport_ceiling"],{"embedding":9,"chat":10})
        self.assertEqual(status["remaining_case_admissions"],{"A":7,"B":2})

    def test_concurrent_same_case_admits_once(self):
        def admit(_):
            try:return self.budget.admit("G1","B",self.paths["G1","B"],self.query())
            except Denied:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(admit,range(2)))
        self.assertEqual(sum(x is not None for x in ids),1)
        self.assertEqual(len(self.budget.status()["admitted_cases"]),1)

    def dispatch_pair(self, attempt):
        token=ACTIVE_ATTEMPT.set(attempt)
        try:
            self.provider.post("https://offline.invalid/v1/embeddings",json={})
            self.provider.post("https://offline.invalid/v1/chat/completions",json={})
            with self.assertRaises(Denied):
                self.provider.post("https://offline.invalid/v1/embeddings",json={})
        finally:ACTIVE_ATTEMPT.reset(token)

    def test_stage_a_eight_stage_b_two_ceiling_and_no_automatic_transition(self):
        for row in self.scopes:
            case,c=row["case"],row["condition"]
            if case in ("CANCEL","FOLLOWUP"):continue
            if case=="G2":
                with closing(sqlite3.connect(self.paths[case,c])) as db,db:
                    db.execute("INSERT INTO Conversations(player_name,npc_name,npc_action) VALUES ('PhaseIIPlayer','Merchant','sell_katana')")
            attempt=self.budget.admit(case,c,self.paths[case,c],self.query(case,c))
            self.dispatch_pair(attempt)
        self.assertEqual(self.budget.status()["transport_reserved_per_kind"],{"embedding":8,"chat":8})
        with self.assertRaises(Denied):
            self.budget.admit("CANCEL","A",self.paths["CANCEL","A"],self.query("CANCEL","A"))
        self.assertEqual(len(self.requests),16)
        review=self.root/"review.md";review.write_text("OFFLINE fixture stage assessment")
        self.budget.enable_stage_b(review)
        first=self.budget.admit("CANCEL","A",self.paths["CANCEL","A"],self.query("CANCEL","A"));self.dispatch_pair(first)
        with self.assertRaises(Denied):
            self.budget.admit("FOLLOWUP","A",self.paths["FOLLOWUP","A"],self.query("FOLLOWUP","A"))
        with closing(sqlite3.connect(self.paths["FOLLOWUP","A"])) as db,db:
            row=db.execute("INSERT INTO Conversations(player_name,npc_name,npc_action) VALUES ('PhaseIIPlayer','Merchant','none')")
            db.execute("CREATE TABLE ActionProposals(conversation_id INTEGER,status TEXT)")
            db.execute("INSERT INTO ActionProposals VALUES (?,'Cancelled')",(row.lastrowid,))
        last=self.budget.admit("FOLLOWUP","A",self.paths["FOLLOWUP","A"],self.query("FOLLOWUP","A"));self.dispatch_pair(last)
        status=self.budget.status()
        self.assertEqual(status["transport_reserved_per_kind"],{"embedding":10,"chat":10})
        self.assertEqual(status["remaining_case_admissions"],{"A":0,"B":0})
        self.assertEqual(len(self.requests),20)
        with self.assertRaises(Denied):specification("STAGE_C","A")

    def test_missing_ledger_and_reinitialisation_cannot_reset_allowance(self):
        missing=self.root/"absent.sqlite3"
        with self.assertRaises(Denied):Budget(missing).status()
        self.assertFalse(missing.exists())
        with self.assertRaises(FileExistsError):
            Budget.initialise(self.root/"budget.sqlite3",self.root/"auth.json",self.root/"audit.json",self.root/"manifest.json")

    def test_enhanced_outcome_save_is_free_and_followup_uses_persisted_cancel(self):
        review=self.root/"stage_a_fixture_review.md";review.write_text("OFFLINE fixture review")
        self.budget.enable_stage_b(review)
        self.chat_action="sell_katana"
        with TestClient(self.app("CANCEL","A")) as client:
            response=client.post("/get_response",json=self.query("CANCEL","A"))
            self.assertEqual(response.status_code,200)
            proposal=response.json()["proposal_id"]
            state={"gold":8,"katana":False,"door_open":None}
            saved=client.post("/actionbridge/outcome",json={
                "proposal_id":proposal,"player_name":"PhaseIIPlayer","status":"Cancelled",
                "before":state,"after":state,"reason":"player_cancelled"})
            self.assertEqual(saved.status_code,200)
            self.assertEqual(len(self.requests),2)
        self.chat_action="none"
        with TestClient(self.app("FOLLOWUP","A")) as client:
            response=client.post("/get_response",json=self.query("FOLLOWUP","A"))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()["action"],"none")
        self.assertEqual(len(self.requests),4)
        self.assertEqual(self.budget.status()["transport_reserved_per_kind"],{"embedding":2,"chat":2})


if __name__=="__main__":
    unittest.main()
