extends Node
## Single-player authority stays in the supplied Godot state and door nodes.
signal outcome_ready(outcome: Dictionary)

var state: Node
var interactions: Node
var records: Dictionary = {}
var pending_id: String = ""

func configure(state_node: Node, interaction_node: Node) -> void:
	state = state_node
	interactions = interaction_node

func _door() -> Node:
	for node in get_tree().get_nodes_in_group("actionbridge_doors"):
		if node.has_method("actionbridge_is_open"):
			return node
	return null

func snapshot() -> Dictionary:
	var door: Node = _door()
	return {
		"gold": int(state.get("gold")), "katana": bool(state.get("katana")),
		"door_open": door.actionbridge_is_open() if door != null else null
	}

func _reason(npc: String, action: String) -> String:
	if not ((npc == "Merchant" and action == "sell_katana") or (npc == "Guard" and action == "open_door")):
		return "wrong_npc_action"
	if action == "sell_katana":
		if bool(state.get("katana")):
			return "already_has_katana"
		if int(state.get("gold")) < 8:
			return "insufficient_gold"
		if not state.has_method("remove_coins_and_gain_katana"):
			return "execution_unavailable"
	else:
		if not bool(state.get("katana")):
			return "no_katana"
		var door: Node = _door()
		if door == null or not interactions.has_signal("open_door"):
			return "door_unavailable"
		if door.actionbridge_is_open():
			return "door_already_open"
	return ""

func propose(proposal_id: String, npc: String, action: String) -> Dictionary:
	if records.has(proposal_id):
		return records[proposal_id].duplicate(true)
	var event: Dictionary = {"proposal_id": proposal_id, "npc_name": npc, "action": action}
	records[proposal_id] = event
	var before: Dictionary = snapshot()
	if not pending_id.is_empty():
		return _finish(event, "Rejected", "another_action_pending", before)
	var reason: String = _reason(npc, action)
	if not reason.is_empty():
		return _finish(event, "Rejected", reason, before)
	pending_id = proposal_id
	event.merge({"status": "Pending", "before": before, "after": before.duplicate(true), "reason": ""})
	event["feedback"] = "Buy the Katana for 8 Gold?" if action == "sell_katana" else "Open the dojo door?"
	return event.duplicate(true)

func resolve(proposal_id: String, confirmed: bool) -> Dictionary:
	if not records.has(proposal_id):
		return {}
	var event: Dictionary = records[proposal_id]
	if event.get("status", "") != "Pending":
		return event.duplicate(true)
	var before: Dictionary = snapshot()
	if not confirmed:
		return _finish(event, "Cancelled", "player_cancelled", before)
	# No await between revalidation and execution.
	var reason: String = _reason(event["npc_name"], event["action"])
	if not reason.is_empty():
		return _finish(event, "Rejected", reason, before)
	if event["action"] == "sell_katana":
		state.remove_coins_and_gain_katana(8)
	else:
		interactions.emit_signal("open_door")
	var after: Dictionary = snapshot()
	var verified: bool = false
	if event["action"] == "sell_katana":
		verified = after["katana"] and after["gold"] == before["gold"] - 8
	else:
		verified = after["door_open"] == true and after["gold"] == before["gold"] and after["katana"] == before["katana"]
	return _finish(event, "Committed" if verified else "Failed", "" if verified else "unverified_execution", before)

func _finish(event: Dictionary, status: String, reason: String, before: Dictionary) -> Dictionary:
	event.merge({"status": status, "reason": reason, "before": before, "after": snapshot()}, true)
	if pending_id == event["proposal_id"]:
		pending_id = ""
	var current: Dictionary = event["after"]
	var state_text: String = "Current state: %d Gold; Katana: %s." % [current["gold"], "yes" if current["katana"] else "no"]
	if status == "Committed":
		event["feedback"] = "Purchase completed. " + state_text if event["action"] == "sell_katana" else "The dojo door is now open."
	elif status == "Cancelled":
		event["feedback"] = "Action cancelled; it was not executed. " + state_text
	else:
		var hints: Dictionary = {
			"insufficient_gold": "Collect enough gold to reach 8 Gold, then try the Merchant.",
			"no_katana": "Obtain a Katana from the Merchant, then return.",
			"already_has_katana": "You already have a Katana; no second purchase is needed.",
			"door_unavailable": "Return to the dojo entrance.",
			"door_already_open": "The door is already open; you can enter.",
			"wrong_npc_action": "Ask the Merchant about buying, or the Guard about entry."
		}
		event["feedback"] = "Action %s. %s %s" % [status.to_lower(), state_text, hints.get(reason, "Check the current state before a new request.")]
	outcome_ready.emit(event.duplicate(true))
	return event.duplicate(true)

func confirm_with_player(proposal_id: String) -> Dictionary:
	var event: Dictionary = records[proposal_id]
	if event["status"] != "Pending":
		return event.duplicate(true)
	var popup := ConfirmationDialog.new()
	popup.title = "Confirm purchase" if event["action"] == "sell_katana" else "Confirm dojo entry"
	popup.dialog_text = event["feedback"] + "\nNo action happens until you confirm."
	popup.ok_button_text = "Confirm"
	popup.cancel_button_text = "Cancel"
	popup.exclusive = true
	popup.confirmed.connect(func(): resolve(proposal_id, true))
	popup.canceled.connect(func(): resolve(proposal_id, false))
	add_child(popup)
	popup.popup_centered(Vector2i(440, 180))
	var result: Dictionary = await outcome_ready
	popup.queue_free()
	return result
