from shruti.stages.gate.admit import _slugify


def test_slugify_sanitizes_filename_and_appends_short_id():
    slug = _slugify("gs://bucket/Physics Projectile 2D!!.mp4", "a1b2c3d4e5f6")
    assert slug == "physics_projectile_2d_a1b2c3d4"


def test_slugify_strips_extension_and_lowercases():
    slug = _slugify("/local/path/Kinematics-Lecture_04.MOV", "ffffffffffff")
    assert slug.startswith("kinematics_lecture_04_")
    assert slug == slug.lower()
