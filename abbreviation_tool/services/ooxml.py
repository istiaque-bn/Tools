import copy
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class CharacterLocation:
    run_index: int
    offset: int
    style_signature: bytes


@dataclass
class TextContainer:
    part: str
    identifier: str
    container_type: str
    text: str
    character_map: list[CharacterLocation]

    def mixed_format(self, start, end):
        styles = {location.style_signature for location in self.character_map[start:end]}
        return len(styles) > 1


def _style_signature(run):
    properties = run.find(f"{W}rPr")
    return ElementTree.tostring(properties) if properties is not None else b""


def paragraph_container(paragraph, part, index, container_type="paragraph"):
    visible = []
    mapping = []
    runs = list(paragraph.iter(f"{W}r"))
    for run_index, run in enumerate(runs):
        signature = _style_signature(run)
        for node in run.iter():
            if node.tag == f"{W}t" and node.text:
                for offset, character in enumerate(node.text):
                    visible.append(character)
                    mapping.append(CharacterLocation(run_index, offset, signature))
            elif node.tag == f"{W}tab":
                visible.append("\t")
                mapping.append(CharacterLocation(run_index, 0, signature))
            elif node.tag in {f"{W}br", f"{W}cr"}:
                visible.append("\n")
                mapping.append(CharacterLocation(run_index, 0, signature))
    return TextContainer(part, f"{part}:p{index}", container_type, "".join(visible), mapping)


def supported_parts(package, include_headers_footers=False, include_footnotes_endnotes=False):
    names = set(package.namelist())
    parts = [("word/document.xml", "body")]
    if include_headers_footers:
        parts.extend((name, "header" if "/header" in name else "footer") for name in sorted(names) if name.startswith(("word/header", "word/footer")) and name.endswith(".xml"))
    if include_footnotes_endnotes:
        parts.extend((name, "footnote" if name.endswith("footnotes.xml") else "endnote") for name in ("word/footnotes.xml", "word/endnotes.xml") if name in names)
    return parts


def document_containers(docx_path, include_tables=True, include_headers_footers=False, include_footnotes_endnotes=False):
    with zipfile.ZipFile(docx_path) as package:
        roots = [(part, part_type, ElementTree.fromstring(package.read(part))) for part, part_type in supported_parts(package, include_headers_footers, include_footnotes_endnotes)]
    containers = []
    for part, part_type, root in roots:
        for index, paragraph in enumerate(root.iter(f"{W}p")):
            in_table = any(ancestor.tag == f"{W}tc" for ancestor in _ancestors(root, paragraph))
            if in_table and not include_tables:
                continue
            container_type = "table" if in_table else ("paragraph" if part_type == "body" else part_type)
            container = paragraph_container(paragraph, part, index, container_type)
            if container.text:
                containers.append(container)
    return containers


def _ancestors(root, target):
    parents = {child: parent for parent in root.iter() for child in parent}
    current = target
    result = []
    while current in parents:
        current = parents[current]
        result.append(current)
    return result
