"""Factory tonal rendering with scale-aware preservation of tiny patterns."""
from scripts import pm99_factory_kit_renderer_v5 as v5

RENDERER_ID = 'pm99-factory-template-kit-v6-scale-aware-patterns-padded-rows'
factory_template_carrier = v5.factory_template_carrier
FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN = v5.FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN
hem_renderer = v5.hem_renderer
_tone_profiles = v5._tone_profiles
_transfer_tone = v5._transfer_tone
_darken = v5._darken


def render_rows(rows, palette, mapper, style):
    native = hem_renderer.boundary_renderer
    mask = [[i != 0 for i in row] for row in rows]
    top, waist = native._shirt_top_and_waist(mask)
    # At 24 pixels wide a valid stripe can be one pixel across. A 3x3 majority
    # filter erases it; retain the artist's original geometry at this scale.
    passes = 0 if rows and len(rows[0]) <= 24 else 2
    regions = native._smoothed_native_regions(rows, palette, mask, top, waist,
                                              smoothing_passes=passes)
    return v5.render_rows(rows, palette, mapper, style, native_regions_override=regions)


def render_template_on_record(target, template, palette, style):
    if (target.width, target.height) != (template.width, template.height):
        raise ValueError('factory template dimensions do not match target')
    bitmap = hem_renderer.boundary_renderer.recipe_renderer
    rows = bitmap.record_to_top_down_indices(template)
    return bitmap.top_down_indices_to_raw(target, render_rows(rows, palette, bitmap.PaletteMapper(palette), style))


def render_record(record, palette, style):
    return render_template_on_record(record, record, palette, style)
