"""Original v1 model/retrieval construction with guarded HTTP clients only.
The frozen adapter factories and prompt are not edited.
"""
import httpx
from adapter.qwen_baseline.contract import Response
from adapter.qwen_baseline.prompt import ORIGINAL_PROMPT_TEMPLATE
from phase2.evaluation.budget_guard import BudgetTransport, NoAsyncProvider


def clients(budget, delegate=None):
    from openai import DefaultHttpxClient
    # This installed SDK defaults to httpx2; the project uses httpx. Preserve
    # the default values without mixing incompatible response-stream classes.
    with DefaultHttpxClient() as original:
        timeout = httpx.Timeout(**original.timeout.as_dict())
        redirects = original.follow_redirects
    return (httpx.Client(transport=BudgetTransport(budget, delegate),
                         timeout=timeout, follow_redirects=redirects),
            httpx.AsyncClient(transport=NoAsyncProvider(),
                              timeout=timeout, follow_redirects=redirects))


def chain(settings, sync_client, async_client):
    from langchain_core.prompts import PromptTemplate
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model=settings.chat_model, temperature=settings.temperature,
        max_tokens=settings.max_tokens, max_retries=0, api_key=settings.api_key,
        base_url=settings.base_url, extra_body={"enable_thinking": settings.enable_thinking},
        http_client=sync_client, http_async_client=async_client,
    )
    prompt = PromptTemplate(template=ORIGINAL_PROMPT_TEMPLATE, input_variables=[
        "player_name", "npc_name", "personality", "allowed_actions", "world_facts",
        "chat_history", "held_items", "player_input",
    ])
    return prompt | llm.with_structured_output(Response, method="json_mode")


def embeddings(settings, sync_client, async_client):
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=settings.embedding_model, dimensions=settings.embedding_dimensions,
        api_key=settings.api_key, base_url=settings.base_url, chunk_size=10,
        check_embedding_ctx_length=False, max_retries=0,
        http_client=sync_client, http_async_client=async_client,
    )


def components(settings, store_path, budget):
    from langchain_community.vectorstores import FAISS
    expected = {"chat_model": "qwen3.7-flash", "embedding_model": "text-embedding-v4",
                "embedding_dimensions": 1024, "temperature": .6,
                "max_tokens": 1024, "enable_thinking": False}
    if any(getattr(settings, k) != v for k, v in expected.items()):
        raise ValueError("Qwen profile differs from Phase II registration")
    if not all((store_path / n).is_file() for n in ("index.faiss", "index.pkl")):
        raise FileNotFoundError("Use the existing validated FAISS index; no build fallback")
    sync_client, async_client = clients(budget)
    store = FAISS.load_local(str(store_path), embeddings(settings, sync_client, async_client),
                             allow_dangerous_deserialization=True)
    if store.index.d != settings.embedding_dimensions:
        raise ValueError("Existing index dimensions differ from registered embeddings")
    return chain(settings, sync_client, async_client), store, (sync_client, async_client)
