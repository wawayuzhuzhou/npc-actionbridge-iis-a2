extends Node
## UI/HTTP coordination only; state authority is ActionBridge + original nodes.
var bridge: Node
var busy: bool = false
var pending_outcome: Dictionary = {}
var last_feedback: String = ""

func _ready() -> void:
	bridge = preload("res://Scripts/ActionBridge.gd").new()
	add_child(bridge)
	bridge.configure(PersistanceManager, InteractionManager)

func has_unsaved_outcome() -> bool:
	return not pending_outcome.is_empty()

func has_pending_confirmation() -> bool:
	return not bridge.pending_id.is_empty()

func handle_response(response: Dictionary, npc: String) -> String:
	var outcome: Dictionary = bridge.propose(str(response["proposal_id"]), npc, str(response["proposed_action"]))
	if outcome["status"] == "Pending":
		outcome = await bridge.confirm_with_player(str(response["proposal_id"]))
	pending_outcome = {
		"proposal_id": outcome["proposal_id"], "player_name": PersistanceManager.player_name,
		"status": outcome["status"], "before": outcome["before"], "after": outcome["after"], "reason": outcome["reason"]
	}
	last_feedback = outcome["feedback"]
	return await retry_save()

func retry_save() -> String:
	if busy or pending_outcome.is_empty():
		return last_feedback
	busy = true
	var request := HTTPRequest.new()
	request.timeout = 10.0
	add_child(request)
	var error: Error = request.request(
		DialogueManager.url + "actionbridge/outcome", ["Content-Type: application/json"],
		HTTPClient.METHOD_POST, JSON.stringify(pending_outcome)
	)
	var saved: bool = false
	if error == OK:
		var completed: Array = await request.request_completed
		if completed[0] == HTTPRequest.RESULT_SUCCESS and completed[1] == 200:
			var payload = JSON.parse_string(completed[3].get_string_from_utf8())
			if payload is Dictionary and payload.has("feedback"):
				last_feedback = payload["feedback"]
				pending_outcome.clear()
				saved = true
	request.queue_free()
	busy = false
	if not saved:
		# Retry only persistence; never execute the action or call the model again.
		return last_feedback + " Result not saved yet. Press Enter to retry saving before another conversation. The action will not run again."
	return last_feedback
