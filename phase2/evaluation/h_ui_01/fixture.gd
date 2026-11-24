extends SceneTree
## Isolated H-UI-01 only. Actual v1 bridge and HUD; no API or model transport.
var journal: FileAccess
var session_id: String = ""
var hud: Node
var feedback: Label
var check_mode: bool = false

func record_event(kind: String, data: Dictionary) -> void:
	var entry: Dictionary = {
		"session_id": session_id, "event": kind,
		"time_utc": Time.get_datetime_string_from_system(true, false) + "Z",
		"unix_time": Time.get_unix_time_from_system(),
		"category": "headless_integration_assertion" if check_mode else "human_GUI_fixture_replay", "provider_requests": 0,
		"network_policy": "offline URL, no HTTP coordination invoked"
	}
	entry.merge(data)
	journal.store_line(JSON.stringify(entry))
	journal.flush()
	print(JSON.stringify(entry))

func hud_flags() -> Dictionary:
	var coins: int = 0
	for i in range(1, 9):
		if hud.get_node("NinePatchRect/MarginContainer/HBoxContainer/TextureRect%d" % i).visible:
			coins += 1
	return {"coin_icons_visible_flag": coins,
		"katana_icon_visible_flag": hud.get_node("NinePatchRect/MarginContainer/HBoxContainer/TextureRect9").visible}

func add_label(text_value: String, position_value: Vector2, size_value: Vector2, font_size: int) -> Label:
	var label := Label.new()
	label.text = text_value
	label.position = position_value
	label.size = size_value
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	var system_font := SystemFont.new()
	system_font.font_names = PackedStringArray(["Segoe UI", "Arial"])
	label.add_theme_font_override("font", system_font)
	root.add_child(label)
	return label

func _initialize() -> void:
	call_deferred("run_fixture")

func run_fixture() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var check_only: bool = "--check-only" in args
	check_mode = check_only
	if not check_only and not "--student-gui" in args:
		printerr("Use --check-only headlessly, or explicit student --student-gui mode.")
		quit(2)
		return
	var output_path: String = ""
	for i in range(args.size() - 1):
		if args[i] == "--session": session_id = args[i + 1]
		if args[i] == "--output": output_path = args[i + 1]
	if session_id.is_empty() or output_path.is_empty() or FileAccess.file_exists(output_path):
		printerr("A new session and unused output path are required; no overwrite.")
		quit(2)
		return
	journal = FileAccess.open(output_path, FileAccess.WRITE)
	if journal == null:
		printerr("Cannot create journal.")
		quit(2)
		return
	root.title = "H-UI-01 Student Fixture Replay - No Model Calls"
	root.size = Vector2i(1180, 720)
	var dialogue: Node = root.get_node("DialogueManager")
	dialogue.set_process_input(false)
	dialogue.set_process_unhandled_input(false)
	dialogue.url = "offline://H-UI-01-disabled/"
	root.get_node("InteractionManager").set_process_input(false)
	var state: Node = root.get_node("PersistanceManager")
	state.player_name = "HUIFixture"
	assert(state.gold == 0 and not state.katana)
	for key in state.existent_items:
		state.pick_up_gold(key)
	hud = load("res://Scenes/UI/HUD.tscn").instantiate()
	root.add_child(hud)
	var bridge: Node = root.get_node("ActionBridgeUI").bridge
	var initial: Dictionary = bridge.snapshot()
	assert(initial.gold == 8 and not initial.katana)
	assert(hud_flags().coin_icons_visible_flag == 8 and not hud_flags().katana_icon_visible_flag)
	record_event("session_started", {"initial_state": initial, "hud_flags": hud_flags(),
		"setup_source": "programmatic original pick_up_gold; not normal gameplay",
		"choice_source": "programmed_offline_assertion" if check_only else "student_only_pending",
		"SQLite_outcome_saving": false})
	if check_only:
		var first: Dictionary = bridge.propose(session_id + "-cancel", "Merchant", "sell_katana")
		assert(first.status == "Pending" and bridge.snapshot() == initial)
		var cancelled: Dictionary = bridge.resolve(first.proposal_id, false)
		assert(cancelled.status == "Cancelled" and cancelled.after == initial)
		assert(hud_flags().coin_icons_visible_flag == 8)
		var second: Dictionary = bridge.propose(session_id + "-confirm", "Merchant", "sell_katana")
		assert(second.status == "Pending" and bridge.snapshot() == initial)
		var committed: Dictionary = bridge.resolve(second.proposal_id, true)
		assert(committed.status == "Committed" and committed.after.gold == 0 and committed.after.katana)
		assert(hud_flags().coin_icons_visible_flag == 0 and hud_flags().katana_icon_visible_flag)
		record_event("headless_assertions_passed", {"category": "headless_integration_assertion",
			"choice_source": "programmed_offline_assertion", "cancelled": cancelled,
			"committed": committed, "hud_flags": hud_flags(), "GUI_buttons_operated": false})
		journal.close()
		quit(0)
		return
	var background := ColorRect.new()
	background.color = Color("14202b")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	root.move_child(background, 0)
	add_label("H-UI-01  Student-operated fixture replay", Vector2(36, 30), Vector2(760, 40), 28)
	add_label("Preset state, actual game controls and HUD. No model call or API/SQLite save.", Vector2(36, 90), Vector2(1100, 60), 20)
	var portrait := TextureRect.new()
	portrait.texture = load("res://Assets/Ninja Adventure/Actor/Characters/OldMan/Faceset.png")
	portrait.position = Vector2(50, 190)
	portrait.size = Vector2(160, 160)
	portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	portrait.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	root.add_child(portrait)
	add_label("Merchant", Vector2(50, 365), Vector2(180, 40), 24)
	feedback = add_label("First purchase proposal: choose Cancel. Save the proposal screen first.", Vector2(245, 480), Vector2(875, 170), 23)
	var pending: Dictionary = bridge.propose(session_id + "-cancel", "Merchant", "sell_katana")
	record_event("purchase_proposal_presented", {"proposal": pending, "hud_flags": hud_flags(), "choice_source": "student_pending"})
	var cancelled: Dictionary = await bridge.confirm_with_player(pending.proposal_id)
	record_event("first_dialog_outcome", {"outcome": cancelled, "hud_flags": hud_flags(),
		"choice_source": "student_ConfirmationDialog_semantic_event", "device_gesture_recorded": false})
	feedback.text = cancelled.feedback
	if cancelled.status != "Cancelled":
		feedback.text += "\nSequence deviation: stop and report; no state reset."
		journal.close()
		return
	await process_frame
	await process_frame
	var next_proposal: Dictionary = bridge.propose(session_id + "-confirm", "Merchant", "sell_katana")
	feedback.text += "\nNew fixture proposal: save this unchanged-state screen, then choose Confirm."
	record_event("second_purchase_proposal_presented", {"proposal": next_proposal, "hud_flags": hud_flags(), "choice_source": "student_pending"})
	var committed: Dictionary = await bridge.confirm_with_player(next_proposal.proposal_id)
	record_event("second_dialog_outcome", {"outcome": committed, "hud_flags": hud_flags(),
		"choice_source": "student_ConfirmationDialog_semantic_event", "device_gesture_recorded": false})
	feedback.text = committed.feedback + "\nSave the final HUD/feedback screen, then close and report."
	journal.close()
