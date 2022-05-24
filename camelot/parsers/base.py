# -*- coding: utf-8 -*-

import os

from ..utils import get_page_layout, get_text_objects


class BaseParser(object):
    """Defines a base parser."""

    def _generate_layout(self, page_info: dict, layout_kwargs: dict):
        self.filename = page_info.get("file", "None")
        self.layout_kwargs = layout_kwargs
        self.layout = page_info.get("layout", None)
        self.dimensions = page_info.get("size", None)
        if self.layout is None or self.dimensions is None:
            self.layout, self.dimensions = get_page_layout(self.filename, **layout_kwargs)
        self.images = get_text_objects(self.layout, ltype="image")
        self.horizontal_text = get_text_objects(self.layout, ltype="horizontal_text")
        self.vertical_text = get_text_objects(self.layout, ltype="vertical_text")
        self.pdf_width, self.pdf_height = self.dimensions
        self.rootname, __ = os.path.splitext(self.filename)
        self.imagename = page_info.get("image", None) or "".join([self.rootname, ".png"])
