"""
This contains functions to export guis in various formats.
"""


import io
import os
import sys
import base64
import numpy as np

from PIL import Image


try:
    import cppimviz as viz
except ModuleNotFoundError:
    sys.path.append(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "../build"))
    import cppimviz as viz

from imviz.common import bundle


class Vertex:

    def __init__(self):

        self.pos = np.array([0.0, 0.0])
        self.uv = np.array([0.0, 0.0])

    def __eq__(self, o):

        return ((self.pos == o.pos).all()
                and (self.uv == o.uv).all())

    def __hash__(self):

        return hash((*self.pos, *self.uv))


class Polygon:

    def __init__(self):

        self.color = ""
        self.alpha = 0.0
        self.vertices = []

        # only used, if the polygon represents one or many characters

        self.text = ""
        self.font_size = 0.0
        self.advance = 0.0
        self.last_char_x = 0.0
        self.last_char_y = 0.0
        self.vertical_text = False

        # only use if we have an image in the polygon

        self.image = None


class DrawListState:

    def __init__(self):

        self.draw_cmds = []
        self.polygon_groups = []

        self.canvas_pos = np.array([0.0, 0.0])
        self.canvas_size = np.array([0.0, 0.0])


def export_polygons(state, dl):

    idxs = dl.get_indices()
    verts = dl.get_verts()

    for cmd in state.draw_cmds:

        polygons = []
        merged_polys = []

        # convert into polygons

        start = cmd.idx_offset
        end = cmd.idx_offset + cmd.elem_count

        for i0, i1, i2 in zip(idxs[start:end:3],
                              idxs[start+1:end:3],
                              idxs[start+2:end:3]):

            c0 = verts[i0].col
            c1 = verts[i1].col
            c2 = verts[i2].col

            alpha0 = ((c0 & 0xff000000) >> 24) / 255
            alpha1 = ((c1 & 0xff000000) >> 24) / 255
            alpha2 = ((c2 & 0xff000000) >> 24) / 255

            alpha = round(max([alpha0, alpha1, alpha2]), 3)

            blue = (c0 & 0x00ff0000) >> 16
            green = (c0 & 0x0000ff00) >> 8
            red = c0 & 0x000000ff

            v0 = Vertex()
            v0.pos = verts[i0].pos
            v0.uv = verts[i0].uv

            v1 = Vertex()
            v1.pos = verts[i1].pos
            v1.uv = verts[i1].uv

            v2 = Vertex()
            v2.pos = verts[i2].pos
            v2.uv = verts[i2].uv

            p = Polygon()
            p.vertices = [v0, v1, v2]
            p.color = f"#{red:02x}{green:02x}{blue:02x}"
            p.alpha = alpha

            polygons.append(p)

        # merge polygons

        if len(polygons) > 0:

            p = polygons[0]

            for o in polygons[1:]:

                if p.color != o.color:
                    merged_polys.append(p)
                    p = o
                    continue

                intersect = list(set(o.vertices) & set(p.vertices))

                if len(intersect) != 2:
                    merged_polys.append(p)
                    p = o
                    continue

                # detected matching side, joining

                p_i0 = p.vertices.index(intersect[0])
                p_i1 = p.vertices.index(intersect[1])
                if p_i1 < p_i0:
                    p_i1, p_i0 = p_i0, p_i1

                excluded_vtxs = list(set(o.vertices) - set(intersect))[0]

                if p_i1 - p_i0 == 1:
                    p.vertices.insert(p_i0+1, excluded_vtxs)
                else:
                    p.vertices.append(excluded_vtxs)

            merged_polys.append(p)

        state.polygon_groups.append(merged_polys)


def export_text_polygons(state):

    # build a character lookup table based on
    # uv coordinates of the font atlas texture

    fonts = viz.get_font_atlas().get_fonts()
    uv_to_char = {}
    for font in fonts:
        for g in font.get_glyphs():
            k = str(g.u0) + str(g.v0)
            c = bytearray([g.codepoint, 0]).decode("utf16")

            v = bundle()
            v.text = c
            v.font_size = font.font_size
            v.advance = g.advance_x

            uv_to_char[k] = v

    # iterate all groups to identify characters

    txt_tex_id = viz.get_font_atlas().get_texture_id()

    for i, (cmd, polys) in enumerate(
            zip(state.draw_cmds, state.polygon_groups)):

        if txt_tex_id != cmd.texture_id:
            continue

        new_polys = []

        for p in polys:

            if len(p.vertices) != 4:
                new_polys.append(p)
                continue

            if (p.vertices[0].uv == p.vertices[1].uv).all():
                new_polys.append(p)
                continue

            # found something with a font texture

            uv0 = np.min(np.array(
                [v.uv for v in p.vertices]), axis=0)

            k = str(float(uv0[0])) + str(float(uv0[1]))

            try:
                char_info = uv_to_char[k]
            except KeyError:
                new_polys.append(p)
                continue

            # seems to be a character

            p.text = char_info.text
            p.font_size = char_info.font_size
            p.advance = char_info.advance
            p.last_char_x, p.last_char_y = np.array(
                    [v.pos for v in p.vertices]).min(axis=0)

            # check if we have vertical text

            min_vtx = min(p.vertices,
                          key=lambda v: v.pos[0]**2 + v.pos[1]**2)
            min_uv = min(p.vertices,
                         key=lambda v: v.uv[0]**2 + v.uv[1]**2)

            p.vertical_text = min_vtx is not min_uv

            # correct y position in case of vertical text

            if p.vertical_text:
                _, p.last_char_y = np.array(
                        [v.pos for v in p.vertices]).max(axis=0)

            # check if we can merge it with a previous char

            if len(new_polys) == 0:
                new_polys.append(p)
                continue

            pp = new_polys[-1]

            if len(pp.text) == 0:
                new_polys.append(p)
                continue

            if p.vertical_text:
                adv_ratio = (pp.last_char_y - p.last_char_y) / pp.advance
                baseline_ok = abs(p.last_char_x - pp.last_char_x) < p.font_size / 2
            else:
                adv_ratio = (p.last_char_x - pp.last_char_x) / pp.advance
                baseline_ok = abs(p.last_char_y - pp.last_char_y) < p.font_size / 2

            can_be_joined = (adv_ratio > 0.5 and adv_ratio < 1.5
                             and baseline_ok
                             and (pp.font_size == p.font_size)
                             and (pp.color == p.color)
                             and (pp.alpha == p.alpha)
                             and (pp.vertical_text == p.vertical_text))

            if not can_be_joined:
                new_polys.append(p)
                continue

            # join and continue

            if adv_ratio > 1.2:
                p.text = " " + p.text

            pp.text += p.text
            pp.vertices += p.vertices
            pp.advance = p.advance
            pp.last_char_x = p.last_char_x
            pp.last_char_y = p.last_char_y

        state.polygon_groups[i] = new_polys


def export_images(state):

    txt_tex_id = viz.get_font_atlas().get_texture_id()

    for cmd, pg in zip(state.draw_cmds, state.polygon_groups):

        if cmd.texture_id == txt_tex_id:
            continue

        # found something with a different texture
        # we need to get that texture!

        texture = viz.get_texture(cmd.texture_id)

        for p in pg:
            p.image = texture


def export_canvas(state):

    canvas_min = np.ones(2) * float("inf")
    canvas_max = np.ones(2) * -float("inf")

    for cmd in state.draw_cmds:
        canvas_min[0] = min(canvas_min[0], cmd.clip_rect[0])
        canvas_min[1] = min(canvas_min[1], cmd.clip_rect[1])
        canvas_max[0] = max(canvas_max[0], cmd.clip_rect[2])
        canvas_max[1] = max(canvas_max[1], cmd.clip_rect[3])

    state.canvas_pos = canvas_min
    state.canvas_size = canvas_max - canvas_min


def export_drawlist_state(dl):

    state = DrawListState()
    state.draw_cmds = dl.get_cmds()

    export_polygons(state, dl)
    export_text_polygons(state)
    export_images(state)
    export_canvas(state)

    return state


def polygon_to_svg(p):

    if p.image is not None:

        np_vtx = np.array([v.pos for v in p.vertices])
        box_min = np_vtx.min(axis=0)
        box_max = np_vtx.max(axis=0)
        box_dims = box_max - box_min

        with io.BytesIO() as fd:
            img = Image.fromarray(p.image)
            img.save(fd, "png")
            fd.seek(0)
            str_img = base64.b64encode(fd.read()).decode("utf8")

        svg_txt = f'<image x="{box_min[0]:.3f}" y="{box_min[1]:.3f}" '
        svg_txt += f'width="{box_dims[0]:.3f}" height="{box_dims[1]:.3f}" '
        svg_txt += 'preserveAspectRatio="none" '
        svg_txt += f'xlink:href="data:image/png;base64,{str_img}" '
        svg_txt += '/>'

        return svg_txt

    if len(p.text) == 0:
        svg_txt = '<polygon points="'

        for i, v in enumerate(p.vertices):
            svg_txt += f'{v.pos[0]:.3f},{v.pos[1]:.3f}'
            if i != len(p.vertices) - 1:
                svg_txt += " "

        svg_txt += f'" fill="{p.color}" fill-opacity="{p.alpha}" />'
    else:
        np_vtx = np.array([v.pos for v in p.vertices])
        box_min = np_vtx.min(axis=0)
        box_max = np_vtx.max(axis=0)
        box_dims = box_max - box_min

        char_size = p.font_size * 0.8

        if p.vertical_text:
            char_x = box_min[0] + p.font_size * 0.55
            char_y = box_min[1] + box_dims[1]
            svg_txt = ('<text '
                       + f'transform="translate({char_x:.3f}, {char_y:.3f}) '
                       + 'rotate(-90)" ')
        else:
            char_x = box_min[0]
            char_y = box_min[1] + p.font_size * 0.55
            svg_txt = f'<text x="{char_x:.3f}" y="{char_y:.3f}" '

        svg_txt += (f'fill="{p.color}" fill-opacity="{p.alpha}" '
                    + 'style="font-family: Source Sans Pro; '
                    + f'font-size: {char_size}px" '
                    + f'>{p.text}</text>')

    return svg_txt


def drawlist_state_to_svg(state):

    # output svg text

    svg_txt = ('<svg version="1.1" '
               + 'viewBox="'
               + f'{state.canvas_pos[0]} '
               + f'{state.canvas_pos[1]} '
               + f'{state.canvas_size[0]} '
               + f'{state.canvas_size[1]}" '
               + 'xmlns="http://www.w3.org/2000/svg" '
               + 'xmlns:xlink="http://www.w3.org/1999/xlink">\n')

    # write clip rects

    svg_txt += "<defs>\n"

    for i, cmd in enumerate(state.draw_cmds):
        cx = cmd.clip_rect[0]
        cy = cmd.clip_rect[1]
        cw = cmd.clip_rect[2] - cx
        ch = cmd.clip_rect[3] - cy
        svg_txt += (f'<clipPath id="clip_rect_{i}">'
                    + f'<rect x="{cx}" y="{cy}" '
                    + f'width="{cw}" height="{ch}" />'
                    + '</clipPath>\n')

    svg_txt += "</defs>\n"

    # write out polygon groups

    for i, pg in enumerate(state.polygon_groups):
        svg_txt += f'<g clip-path="url(#clip_rect_{i})">\n'
        for p in pg:
            svg_txt += polygon_to_svg(p) + "\n"
        svg_txt += '</g>\n'

    # close and return

    svg_txt += '</svg>\n'

    return svg_txt


plot_to_export = -1


def begin_plot(*args, **kwargs):

    res = viz.begin_plot(*args, **kwargs)

    global plot_to_export

    if plot_to_export == viz.get_plot_id():
        viz.disable_aa()

    return res


def end_plot():

    dl = viz.get_window_drawlist()

    export_requested = False

    current_plot_id = viz.get_plot_id()

    viz.push_override_id(current_plot_id)
    if viz.begin_popup("##PlotContext"):
        if viz.begin_menu("Export"):
            if viz.menu_item("As svg"):
                export_requested = True
            viz.end_menu()
        viz.separator()
        viz.end_popup()
    viz.pop_id()

    viz.end_plot()

    global plot_to_export

    if plot_to_export == current_plot_id:

        dl_state = export_drawlist_state(dl)
        svg_txt = drawlist_state_to_svg(dl_state)

        with open("test.svg", "w+") as fd:
            fd.write(svg_txt)

        plot_to_export = -1

    if export_requested:
        plot_to_export = current_plot_id
