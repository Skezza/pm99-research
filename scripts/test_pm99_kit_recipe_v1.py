from pathlib import Path

from PIL import Image, ImageDraw

from scripts.pm99_kit_recipe_v1 import recipe_from_source


def _striped_source(path: Path, orientation: str) -> None:
    image = Image.new("RGBA", (40, 60), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 3, 35, 56), radius=4, fill=(190, 5, 30, 255))
    if orientation == "vertical":
        for x in range(5, 36, 10):
            draw.rectangle((x, 4, x + 4, 55), fill=(8, 35, 108, 255))
    else:
        for y in range(5, 56, 10):
            draw.rectangle((5, y, 34, y + 4), fill=(8, 35, 108, 255))
    image.save(path)


def test_recipe_classifies_vertical_stripes_without_copying_source_pixels(tmp_path: Path) -> None:
    path = tmp_path / "vertical.png"
    _striped_source(path, "vertical")
    recipe = recipe_from_source(path)
    assert recipe["pattern"] == "vertical_stripes"
    assert recipe["renderer"] == "pm99-abstract-kit-recipe-v1"
    assert len(recipe["colors"]) == 2
    assert all(len(colour) == 3 for colour in recipe["colors"])


def test_recipe_classifies_hoops_without_copying_source_pixels(tmp_path: Path) -> None:
    path = tmp_path / "horizontal.png"
    _striped_source(path, "horizontal")
    recipe = recipe_from_source(path)
    assert recipe["pattern"] == "hoops"
