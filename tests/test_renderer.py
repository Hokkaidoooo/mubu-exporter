import urllib.parse

import pytest
from markdown_it import MarkdownIt

from mubu_exporter.errors import ExportError
from mubu_exporter.renderer import (
    RenderOptions, collect_image_uris, relative_link, render_inline, render_nodes,
)


@pytest.mark.parametrize(("source", "expected"), [
    ('<span class="bold">A</span><span class="bold">B</span>', "**AB**"),
    ('<span class="highlight-yellow">A</span><span class="bold highlight-yellow">B</span>', "==A**B**=="),
    ('<span class="formula" data-raw="x%5E2"><br>ignored</span>TAIL', "$x^2$TAIL"),
    ('<span class="row-select-btn"><input>hidden</span>TAIL', "TAIL"),
    ('<b>A<br>B</b>', "**A**\n**B**"),
    ('<b>A<br/>B</b>', "**A**\n**B**"),
    ('<span class="mask">ABC</span>', "{{ABC}}"),
    ('<span class="strikethrough">ABC</span>', "~~ABC~~"),
    ('<u>ABC</u>', "<u>ABC</u>"),
    ('<span>👩\u200d💻</span>', "👩\u200d💻"),
])
def test_rich_text(source, expected):
    assert render_inline(source, RenderOptions())[0] == expected


def test_table_keeps_literal_angle_brackets_and_escaped_pipe():
    _, tables = render_inline('<table><tr><td>&lt;T&gt;</td><td>A|B<br>C</td></tr></table>', RenderOptions())
    assert "\\<T>" in tables[0]
    parsed = MarkdownIt("commonmark").enable("table").render(tables[0])
    assert "&lt;T&gt;" in parsed
    assert "A|B<br" in parsed


@pytest.mark.parametrize("source", [
    '<table><tr><td colspan="2">A</td></tr></table>',
    '<table><tr><td rowspan="2">A</td></tr></table>',
    '<table><tr><td><table><tr><td>A</td></tr></table></td></tr></table>',
    '<table><tr><td>A</td></tr>',
    '<span class="formula" data-raw="x">',
])
def test_unrepresentable_or_unclosed_html_fails(source):
    with pytest.raises(ExportError):
        render_inline(source, RenderOptions())


@pytest.mark.parametrize("literal", ["a`b", "a``b", "a  b", " `x` ", "   "])
def test_code_characters_survive_markdown_parse(literal):
    rendered, _ = render_inline(f'<span class="codespan">{literal}</span>', RenderOptions())
    html = MarkdownIt().render(rendered)
    assert f"<code>{literal}</code>" in html


@pytest.mark.parametrize("source", [
    '<a href="javascript:alert(1)">go</a>',
    '<a href="data:text/html,hello">go</a>',
    '<font color="red;position:absolute">A</font>',
    '<font color="red&quot; onclick=&quot;alert(1)">A</font>',
])
def test_unsafe_input_is_explicit(source):
    with pytest.raises(ExportError):
        render_inline(source, RenderOptions())


def test_trusted_input_is_an_explicit_switch():
    text, _ = render_inline('<a href="custom:example">go</a>', RenderOptions(preserve_unsafe=True))
    assert "custom:example" in text


def test_mention_points_to_existing_anchor():
    label = urllib.parse.quote('[{"text":"Target"}]')
    source = f'<span class="node-mention" data-doc="other" data-node="node_2" data-text="{label}">Target</span>'
    text, _ = render_inline(source, RenderOptions(doc_paths={"other": "A # B.md"}))
    target = "\n".join(render_nodes([{"id": "node_2", "text": "Target"}], RenderOptions()))
    assert "A%20%23%20B.md#node_2" in text
    assert '<a id="node_2"></a>' in target


@pytest.mark.parametrize("mode", ["remote", "local", "skip"])
def test_inline_and_attached_images_share_policy(mode):
    uri = "https://example.com/image.png"
    opts = RenderOptions(image_mode=mode, image_names={uri: "sample.png"})
    nodes = [{"text": f'<img src="{uri}">', "images": [{"uri": uri}]}]
    result = "\n".join(render_nodes(nodes, opts))
    if mode == "skip":
        assert "![]" not in result
    else:
        assert result.count("![]") == 2
        assert ("images/sample.png" if mode == "local" else uri) in result


def test_local_images_never_silently_use_remote_urls():
    with pytest.raises(ExportError):
        render_nodes([{"text": '<img src="https://example.com/image.png">'}], RenderOptions(image_mode="local"))


def test_collects_images_from_children_notes_and_tables():
    nodes = [{"text": '<table><tr><td><img src="a.png"></td></tr></table>',
              "note": '<img src="b.png">', "children": [{"images": [{"uri": "c.png"}]}]}]
    assert collect_image_uris(nodes) == ["a.png", "b.png", "c.png"]


def test_task_status_does_not_invent_checkboxes():
    nodes = [{"text": "ordinary", "finish": True}, {"text": "todo", "taskStatus": 1},
             {"text": "done", "taskStatus": 2}]
    text = "\n".join(render_nodes(nodes, RenderOptions()))
    assert "- ordinary" in text
    assert "- [ ] todo" in text and "- [x] done" in text


def test_relative_paths_escape_fragment_and_space():
    assert relative_link("甲", "乙/A # B.md") == "../乙/A%20%23%20B.md"


def test_paragraph_boundaries_and_link_labels_survive_rendering():
    text, _ = render_inline('<p>A</p><p>B</p><a href="https://example.com">[label]</a>', RenderOptions())
    assert text.startswith("A\nB\n")
    parsed = MarkdownIt().render(text)
    assert '<a href="https://example.com">[label]</a>' in parsed


def test_table_ui_elements_do_not_swallow_following_content():
    source = '<table><tr><td><span class="row-select-btn"><input>UI</span>Value</td></tr></table>TAIL'
    text, tables = render_inline(source, RenderOptions())
    assert text == "TAIL"
    assert "Value" in tables[0] and "UI" not in tables[0]


def test_external_mention_preserves_source_link():
    source = '<span class="node-mention" data-doc="external_example" data-text="%5B%7B%22text%22%3A%22Example%22%7D%5D">Example</span>'
    result, _ = render_inline(source, RenderOptions())
    assert result == "[Example](https://mubu.com/doc/external_example)"


@pytest.mark.parametrize("source", [
    '<table><tr><td>A</tr></table>',
    '<table><tr><td>A<td>B</td></tr></table>',
    '<table><caption>Caption</caption><tr><td>A</td></tr></table>',
])
def test_table_does_not_silently_drop_unrepresentable_text(source):
    with pytest.raises(ExportError):
        render_inline(source, RenderOptions())
