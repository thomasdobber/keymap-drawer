"""
Given keymap description with layers and combos (in a yaml), and physical
keyboard layout definition (either via QMK info files or using a parametrized
ortho layout), print an SVG representing the keymap to standard output.
"""

import sys
from argparse import ArgumentParser, FileType, Namespace
from importlib.metadata import version
from pathlib import Path

import yaml

from keymap_drawer.config import Config
from keymap_drawer.draw import KeymapDrawer
from keymap_drawer.keymap import KeymapData
from keymap_drawer.parse import QmkJsonParser, ZmkKeymapParser


def draw(args: Namespace, config: Config) -> None:
    """Draw the keymap in SVG format to stdout."""
    yaml_data = yaml.safe_load(args.keymap_yaml)
    assert "layers" in yaml_data, 'Keymap needs to be specified via the "layers" field in keymap_yaml'

    if args.qmk_keyboard or args.qmk_info_json or args.dts_layout or args.ortho_layout or args.cols_thumbs_notation:
        layout = {
            "qmk_keyboard": args.qmk_keyboard,
            "qmk_info_json": args.qmk_info_json,
            "dts_layout": args.dts_layout,
            "layout_name": args.layout_name,
            "ortho_layout": args.ortho_layout,
            "cols_thumbs_notation": args.cols_thumbs_notation,
        }
    else:
        assert "layout" in yaml_data, (
            "A physical layout needs to be specified either via "
            "--qmk-keyboard/--qmk-info-json/--dts-layout/--ortho-layout/--cols-thumbs-notation, "
            'or in a "layout" field in the keymap_yaml'
        )
        layout = yaml_data["layout"]

    if custom_config := yaml_data.get("draw_config"):
        config.draw_config = config.draw_config.model_copy(update=custom_config)

    drawer = KeymapDrawer(
        config=config,
        out=args.output,
        layers=yaml_data["layers"],
        layout=layout,
        combos=yaml_data.get("combos", []),
    )
    drawer.print_board(
        draw_layers=args.select_layers,
        keys_only=args.keys_only,
        combos_only=args.combos_only,
        ghost_keys=args.ghost_keys,
    )


def parse(args: Namespace, config: Config) -> None:
    """Call the appropriate parser for given args and dump YAML keymap representation to stdout."""
    if args.base_keymap:
        yaml_data = yaml.safe_load(args.base_keymap)
        base = KeymapData(layers=yaml_data["layers"], combos=yaml_data.get("combos", []), layout=None, config=None)
    else:
        base = None

    if args.qmk_keymap_json:
        parsed = QmkJsonParser(config.parse_config, args.columns, base_keymap=base, layer_names=args.layer_names).parse(
            args.qmk_keymap_json
        )
    else:
        parsed = ZmkKeymapParser(
            config.parse_config, args.columns, base_keymap=base, layer_names=args.layer_names
        ).parse(args.zmk_keymap)

    yaml.safe_dump(parsed, args.output, width=160, sort_keys=False, default_flow_style=None, allow_unicode=True)


def dump_config(args: Namespace, config: Config) -> None:
    """Dump the currently active config, either default or parsed from args."""

    def cfg_str_representer(dumper, in_str):
        if "\n" in in_str:  # use '|' style for multiline strings
            return dumper.represent_scalar("tag:yaml.org,2002:str", in_str, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", in_str)

    yaml.representer.SafeRepresenter.add_representer(str, cfg_str_representer)
    yaml.safe_dump(config.model_dump(), args.output, sort_keys=False, allow_unicode=True)


def main() -> None:
    """Parse the configuration and print SVG using KeymapDrawer."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--version", action="version", version=version("keymap-drawer"))
    parser.add_argument(
        "-c",
        "--config",
        help="A YAML file containing settings for parsing and drawing, "
        "default can be dumped using `dump-config` command and to be modified",
        type=FileType("rt", encoding="utf-8"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    draw_p = subparsers.add_parser("draw", help="draw an SVG representation of the keymap")
    info_srcs = draw_p.add_mutually_exclusive_group()
    info_srcs.add_argument(
        "-j",
        "--qmk-info-json",
        help="Path to QMK info.json for a keyboard, containing the physical layout description",
        type=Path,
    )
    info_srcs.add_argument(
        "-k",
        "--qmk-keyboard",
        help="Name of the keyboard in QMK to fetch info.json containing the physical layout info, "
        "including revision if any",
    )
    info_srcs.add_argument(
        "-d",
        "--dts-layout",
        help="Path to file containing ZMK physical layout definition in devicetree format",
        type=Path,
    )
    draw_p.add_argument(
        "-l",
        "--layout-name",
        "--qmk-layout",
        help='Name of the layout to use in the QMK keyboard info file (starting with "LAYOUT_"), '
        "or ZMK DTS physical layout (node name). Use the first defined one if not specified",
    )
    draw_p.add_argument(
        "--ortho-layout",
        help="Parametrized ortholinear layout definition in a YAML format, "
        "for example '{split: false, rows: 4, columns: 12}'",
        type=yaml.safe_load,
    )
    draw_p.add_argument(
        "-n",
        "--cols-thumbs-notation",
        help='Parametrized ortholinear layout definition in "cols+thumbs" notation, '
        "for example '23332+2 2+33331' for an asymmetric 30 key split keyboard",
    )
    draw_p.add_argument("-s", "--select-layers", help="A list of layer names to draw, draw all by default", nargs="+")
    draw_p.add_argument("--keys-only", help="Only draw keys, not combos on layers", action="store_true")
    draw_p.add_argument("--combos-only", help="Only draw combos, not keys on layers", action="store_true")
    draw_p.add_argument(
        "-g",
        "--ghost-keys",
        help="A list of zero-based key indices to assign `type: ghost` in all drawn layers",
        nargs="+",
        type=int,
    )
    draw_p.add_argument(
        "keymap_yaml",
        help='YAML file (or stdin for "-") containing keymap definition with layers and (optionally) combos, '
        "see README for schema",
        type=FileType("rt", encoding="utf-8"),
    )
    draw_p.add_argument(
        "-o",
        "--output",
        help="Output to path instead of stdout",
        type=FileType("wt", encoding="utf-8"),
        default=sys.stdout,
    )

    parse_p = subparsers.add_parser(
        "parse", help="parse a QMK/ZMK keymap to YAML representation to stdout, to be used with the `draw` command"
    )
    keymap_srcs = parse_p.add_mutually_exclusive_group(required=True)
    keymap_srcs.add_argument(
        "-q", "--qmk-keymap-json", help="Path to QMK keymap.json to parse", type=FileType("rt", encoding="utf-8")
    )
    keymap_srcs.add_argument(
        "-z", "--zmk-keymap", help="Path to ZMK *.keymap to parse", type=FileType("rt", encoding="utf-8")
    )
    parse_p.add_argument(
        "-b",
        "--base-keymap",
        help="A base keymap YAML to inherit certain properties from",
        type=FileType("rt", encoding="utf-8"),
    )
    parse_p.add_argument(
        "-l",
        "--layer-names",
        help="List of layer names to override parsed names; its length should match the number of layers",
        nargs="+",
    )
    parse_p.add_argument(
        "-c",
        "--columns",
        help="Number of columns in the layout to enable better key grouping in the output, optional",
        type=int,
    )
    parse_p.add_argument(
        "-o",
        "--output",
        help="Output to path instead of stdout",
        type=FileType("wt", encoding="utf-8"),
        default=sys.stdout,
    )

    dump_p = subparsers.add_parser(
        "dump-config", help="dump default draw and parse config to stdout that can be passed to -c/--config option"
    )
    dump_p.add_argument(
        "-o",
        "--output",
        help="Output to path instead of stdout",
        type=FileType("wt", encoding="utf-8"),
        default=sys.stdout,
    )

    args = parser.parse_args()

    config = Config.parse_obj(yaml.safe_load(args.config)) if args.config else Config()

    match args.command:
        case "draw":
            draw(args, config)
        case "parse":
            parse(args, config)
        case "dump-config":
            dump_config(args, config)


if __name__ == "__main__":
    main()
