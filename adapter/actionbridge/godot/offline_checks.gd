extends SceneTree
## E2 injected-action fixtures using real enhanced Godot state/door functions.
var checks: int = 0
var failures: int = 0

func _initialize() -> void:
	call_deferred("_run")

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		print("FAIL: ", label)

func _run() -> void:
	var state: Node = root.get_node("PersistanceManager")
	var bridge: Node = root.get_node("ActionBridgeUI").bridge
	var dojo: Node = load("res://Scenes/Structures/dojo.tscn").instantiate()
	root.add_child(dojo)
	for gold in [0, 7]:
		state.gold = gold
		state.katana = false
		var rejected: Dictionary = bridge.propose("low-" + str(gold), "Merchant", "sell_katana")
		check(rejected["status"] == "Rejected" and state.gold == gold and not state.katana, "insufficient gold is rejected without mutation")
	state.gold = 8
	check(bridge.propose("wrong-npc", "Mother", "sell_katana")["status"] == "Rejected", "NPC permission checked")
	check(bridge.propose("no-katana", "Guard", "open_door")["status"] == "Rejected", "Guard requires actual Katana")
	check(not dojo.actionbridge_is_open(), "rejected Guard leaves real door closed")
	var pending: Dictionary = bridge.propose("cancel", "Merchant", "sell_katana")
	check(pending["status"] == "Pending" and state.gold == 8 and not state.katana, "no inventory mutation before confirmation")
	check(bridge.resolve("cancel", false)["status"] == "Cancelled" and state.gold == 8 and not state.katana, "cancel preserves inventory")
	bridge.propose("revalidate", "Merchant", "sell_katana")
	state.gold = 7
	check(bridge.resolve("revalidate", true)["status"] == "Rejected" and not state.katana, "state is revalidated at confirmation")
	state.gold = 8
	bridge.propose("purchase", "Merchant", "sell_katana")
	check(bridge.resolve("purchase", true)["status"] == "Committed" and state.gold == 0 and state.katana, "real purchase commits once")
	bridge.resolve("purchase", true)
	check(state.gold == 0 and state.katana, "duplicate confirmation does not charge again")
	state.gold = 8
	check(bridge.propose("repeat-purchase", "Merchant", "sell_katana")["status"] == "Rejected" and state.gold == 8, "new duplicate purchase rejected")
	bridge.propose("door", "Guard", "open_door")
	check(not dojo.actionbridge_is_open(), "door not opened before confirmation")
	check(bridge.resolve("door", true)["status"] == "Committed" and dojo.actionbridge_is_open(), "real door visibility and collision verified")
	dojo.free()
	dojo = load("res://Scenes/Structures/dojo.tscn").instantiate()
	root.add_child(dojo)
	check(dojo.actionbridge_is_open(), "committed door state survives scene recreation")
	check(bridge.propose("repeat-door", "Guard", "open_door")["status"] == "Rejected", "repeat door action does not execute again")
	state.katana = false
	state.gold = 10
	bridge.propose("price", "Merchant", "sell_katana")
	bridge.resolve("price", true)
	check(state.gold == 2 and state.katana, "enhanced existing purchase function honors 8 Gold price")
	# Exercise the actual ConfirmationDialog controls; this is not a user study.
	state.katana = false
	state.gold = 8
	bridge.propose("popup-cancel", "Merchant", "sell_katana")
	call_deferred("_show_popup", bridge, "popup-cancel")
	await process_frame
	var popup: ConfirmationDialog = _popup(bridge)
	check(popup != null and popup.ok_button_text == "Confirm" and popup.cancel_button_text == "Cancel", "visible choice labels configured")
	popup.get_cancel_button().pressed.emit()
	await process_frame
	check(state.gold == 8 and not state.katana and bridge.records["popup-cancel"]["status"] == "Cancelled", "Cancel button cancels without mutation")
	bridge.propose("popup-confirm", "Merchant", "sell_katana")
	call_deferred("_show_popup", bridge, "popup-confirm")
	await process_frame
	_popup(bridge).get_ok_button().pressed.emit()
	await process_frame
	check(state.gold == 0 and state.katana and bridge.records["popup-confirm"]["status"] == "Committed", "Confirm button commits purchase")
	dojo.queue_free()
	await process_frame
	await process_frame
	print(JSON.stringify({"evidence_category": "E2 deterministic injected-action Godot checks", "checks": checks, "failures": failures, "provider_requests": 0}))
	quit(0 if failures == 0 else 1)

func _show_popup(bridge: Node, proposal_id: String) -> void:
	await bridge.confirm_with_player(proposal_id)

func _popup(bridge: Node) -> ConfirmationDialog:
	for child in bridge.get_children():
		if child is ConfirmationDialog:
			return child
	return null
