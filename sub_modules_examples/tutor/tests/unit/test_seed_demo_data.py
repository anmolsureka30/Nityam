
from app.memory import store
from scripts.seed_demo_data import parse_wiki_file, seed

FIXTURE = """# Horizontal Range
`horizontal_range`


## Taught in shruti:d_jnekwca6i_4c5411d0 @3:40
The total horizontal distance traveled by a projectile from its launch point.

**Board:**
- [equation] R = u cos theta * t

## Taught in shruti:d_jnekwca6i_4c5411d0 @9:12
A second explanation, later in the same lecture.
"""


def test_parse_wiki_file_splits_on_taught_in_sections(tmp_path):
    wiki_file = tmp_path / "horizontal_range.md"
    wiki_file.write_text(FIXTURE)

    chunks = parse_wiki_file(wiki_file)

    assert len(chunks) == 2
    assert chunks[0].source_ref == "shruti:d_jnekwca6i_4c5411d0"
    assert chunks[0].location == "3:40"
    assert chunks[0].concept_ids == ["projectile.horizontal_range"]
    assert "total horizontal distance" in chunks[0].text
    assert chunks[1].location == "9:12"
    assert chunks[0].chunk_id != chunks[1].chunk_id


def test_seed_populates_grounding_and_demo_student():
    conn = store.connect(":memory:")
    seed(conn)

    results = store.search_grounding(conn, ["projectile.horizontal_range"])
    assert len(results) > 0

    profile = store.get_dpm(conn, "demo_student")
    assert profile is not None
    assert profile.student_id == "demo_student"

    memory = store.get_teaching_memory(conn, "demo_student")
    assert memory is not None
    assert "projectile.horizontal_range" in memory.syllabus
    conn.close()
