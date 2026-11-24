extends SceneTree
## Offline E2 replay: actual copied v1 state and door functions, no HTTP.
func _initialize() -> void:
	call_deferred("_run")

func snapshot(state: Node, dojo: Node) -> Dictionary:
	return {"gold": int(state.gold), "katana": bool(state.katana),
		"door_open": dojo.collision_shape_door.disabled and not dojo.door_closed.visible}

func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var state: Node = root.get_node("PersistanceManager")
	state.gold = job["case"]["gold"]
	state.katana = job["case"]["katana"]
	state.player_name = "PhaseIIPlayer"
	if job["condition"] == "A":
		state.actionbridge_dojo_open = false
	var dojo: Node = load("res://Scenes/Structures/dojo.tscn").instantiate()
	root.add_child(dojo)
	var before: Dictionary = snapshot(state, dojo)
	var result: Dictionary = {}
	if job["condition"] == "B":
		var dialogue: Node = root.get_node("DialogueManager")
		dialogue._on_request_completed(HTTPRequest.RESULT_SUCCESS, 200, [], JSON.stringify(job["response"]).to_utf8_buffer())
		result = {"status": "BaselineDispatched", "reason": ""}
	else:
		var bridge: Node = root.get_node("ActionBridgeUI").bridge
		result = bridge.propose(job["response"]["proposal_id"], job["case"]["npc"], job["response"]["proposed_action"])
		assert(snapshot(state, dojo) == before, "Proposal must not mutate state")
		if result["status"] == "Pending":
			result = bridge.resolve(job["response"]["proposal_id"], job["case"]["choice"] == "Confirm")
	var observed: Dictionary = {"before": before, "after": snapshot(state, dojo),
		"status": result["status"], "reason": result["reason"],
		"choice_source": "deterministic fixture; no human button interaction", "provider_requests": 0}
	var output := FileAccess.open(args[1], FileAccess.WRITE)
	output.store_string(JSON.stringify(observed))
	output.close()
	quit(0)
