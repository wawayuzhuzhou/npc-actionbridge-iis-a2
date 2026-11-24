"""Create a separately labelled enhanced game; never patch baseline/frozen files."""
import argparse
from pathlib import Path
import shutil


def prepare(source_game: Path, source_db: Path, target: Path) -> Path:
    source_game, source_db, target = source_game.resolve(), source_db.resolve(), target.resolve()
    if target.exists():
        raise FileExistsError("Refusing to overwrite an existing enhanced runtime")
    if any(p.lower() == "upstream_frozen" for p in target.parts) or target == source_game or source_game in target.parents:
        raise ValueError("Enhanced runtime must be separate from baseline/frozen source")
    dialogue = (source_game / "Scripts/DialogueManager.gd").read_text(encoding="utf-8")
    assert 'var url = "http://127.0.0.1:8000/"' in dialogue
    assert "\tvar message = response[\"response\"]" in dialogue
    assert "ActionBridgeUI" not in dialogue
    game = target / "game"
    # Reuse already imported assets by copying the disposable import cache.
    shutil.copytree(source_game, game, ignore=shutil.ignore_patterns(".git"))
    target.joinpath("api_runtime").mkdir()
    shutil.copy2(source_db, target / "api_runtime/game_data.db")
    for script in Path(__file__).with_name("godot").glob("*.gd"):
        shutil.copy2(script, game / "Scripts" / script.name)
    config = (game / "project.godot").read_text(encoding="utf-8")
    config = config.replace('config/name="Generative NPC Dialogue"', 'config/name="NPC ActionBridge"')
    config = config.replace('DialogueManager="*res://Scenes/DialogueManager.tscn"',
                            'DialogueManager="*res://Scenes/DialogueManager.tscn"\nActionBridgeUI="*res://Scripts/ActionBridgeUI.gd"')
    (game / "project.godot").write_text(config, encoding="utf-8")
    dialogue = dialogue.replace('var url = "http://127.0.0.1:8000/"', 'var url = "http://127.0.0.1:8001/"')
    dialogue = dialogue.replace("func _input(event):\n", """func _input(event):
	if ActionBridgeUI.busy or ActionBridgeUI.has_pending_confirmation():
		return
	if ActionBridgeUI.has_unsaved_outcome() and event.is_action_pressed("ui_accept") and is_dialogue_active:
		get_viewport().set_input_as_handled()
		await _retry_bridge_save()
		return
""")
    dialogue = dialogue.replace('\tvar message = response["response"]', """	if response.get("proposal_id") != null:
		var feedback: String = await ActionBridgeUI.handle_response(response, str(npc_type))
		dialogue_lines.push_back(feedback)
		print("ActionBridge feedback: ", feedback)
		request_finished.emit()
		return
	var message = response["response"]""")
    dialogue = dialogue.replace("\tnpc_type = type\n", """	npc_type = type
	if ActionBridgeUI.has_unsaved_outcome():
		var feedback: String = await ActionBridgeUI.retry_save()
		if ActionBridgeUI.has_unsaved_outcome():
			dialogue_lines.push_back(feedback)
			_show_text_box()
			is_dialogue_active = true
			return
""")
    dialogue += """
func _retry_bridge_save():
	var feedback: String = await ActionBridgeUI.retry_save()
	dialogue_lines.push_back(feedback)
	if text_box:
		text_box.queue_free()
	_show_text_box()
"""
    (game / "Scripts/DialogueManager.gd").write_text(dialogue, encoding="utf-8")
    persistence = game / "Scripts/PersistanceManager.gd"
    text = persistence.read_text(encoding="utf-8")
    old = "func remove_coins_and_gain_katana(price: int):\n\tgold = 0"
    assert old in text
    # Honor the existing price argument; equivalent to upstream at natural 8 Gold.
    text = text.replace(old, "func remove_coins_and_gain_katana(price: int):\n\tgold -= price")
    text = text.replace("@export var katana: bool", "@export var katana: bool\nvar actionbridge_dojo_open: bool = false")
    persistence.write_text(text, encoding="utf-8")
    dojo = game / "Scenes/Structures/dojo.gd"
    text = dojo.read_text(encoding="utf-8").replace('func _ready():\n', 'func _ready():\n\tadd_to_group("actionbridge_doors")\n')
    text = text.replace("\tInteractionManager.open_door.connect(_on_opened_door)", """	InteractionManager.open_door.connect(_on_opened_door)
	if PersistanceManager.actionbridge_dojo_open:
		collision_shape_door.disabled = true
		door_closed.hide()""")
    text = text.replace("func _on_opened_door():\n", "func _on_opened_door():\n\tPersistanceManager.actionbridge_dojo_open = true\n")
    text += '\nfunc actionbridge_is_open() -> bool:\n\treturn collision_shape_door.disabled and not door_closed.visible\n'
    dojo.write_text(text, encoding="utf-8")
    return game


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-game", type=Path, required=True)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.source_game, args.source_db, args.target))
