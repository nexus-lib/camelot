# -*- coding: utf-8 -*-

import os
import sys

from PyPDF2 import PdfFileReader, PdfFileWriter

from .core import TableList
from .parsers import Stream, Lattice
from .utils import (
    TemporaryDirectory,
    get_page_layout,
    get_text_objects,
    get_rotation,
    is_url,
    download_url,
)

from typing import List

class PDFHandler(object):
    """Handles all operations like temp directory creation, splitting
    file into single page PDFs, parsing each PDF and then removing the
    temp directory.

    Parameters
    ----------
    filepath : str
        Filepath or URL of the PDF file.
    pages : str, optional (default: '1')
        Comma-separated page numbers.
        Example: '1,3,4' or '1,4-end' or 'all'.
    password : str, optional (default: None)
        Password for decryption.

    """

    def __init__(self, filepath, pages="1", password=None):
        if is_url(filepath):
            filepath = download_url(filepath)
        self.filepath = filepath
        if not filepath.lower().endswith(".pdf"):
            raise NotImplementedError("File format not supported")

        if password is None:
            self.password = ""
        else:
            self.password = password
            if sys.version_info[0] < 3:
                self.password = self.password.encode("ascii")
        self.pages = self._get_pages(pages)

    def _get_pages(self, pages):
        """Converts pages string to list of ints.

        Parameters
        ----------
        filepath : str
            Filepath or URL of the PDF file.
        pages : str, optional (default: '1')
            Comma-separated page numbers.
            Example: '1,3,4' or '1,4-end' or 'all'.

        Returns
        -------
        P : list
            List of int page numbers.

        """
        page_numbers = []

        if pages.isdigit():
            page_numbers.append({"start": int(pages), "end": int(pages)})
        else:
            with open(self.filepath, "rb") as f:
                infile = PdfFileReader(f, strict=False)

                if infile.isEncrypted:
                    infile.decrypt(self.password)

                if pages == "all":
                    page_numbers.append({"start": 1, "end": infile.getNumPages()})
                else:
                    for r in pages.split(","):
                        if "-" in r:
                            a, b = r.split("-")
                            if b == "end":
                                b = infile.getNumPages()
                            page_numbers.append({"start": int(a), "end": int(b)})
                        else:
                            page_numbers.append({"start": int(r), "end": int(r)})

        P = []
        for p in page_numbers:
            P.extend(range(p["start"], p["end"] + 1))
        return sorted(set(P))

    def _save_page(self, filepath, page, temp):
        """Saves specified page from PDF into a temporary directory.

        Parameters
        ----------
        filepath : str
            Filepath or URL of the PDF file.
        page : int
            Page number.
        temp : str
            Tmp directory.

        """
        with open(filepath, "rb") as fileobj:
            infile = PdfFileReader(fileobj, strict=False)
            if infile.isEncrypted:
                infile.decrypt(self.password)
            fpath = os.path.join(temp, f"page-{page}.pdf")
            froot, fext = os.path.splitext(fpath)
            p = infile.getPage(page - 1)
            outfile = PdfFileWriter()
            outfile.addPage(p)
            with open(fpath, "wb") as f:
                outfile.write(f)
            layout, dim = get_page_layout(fpath)
            # fix rotated PDF
            chars = get_text_objects(layout, ltype="char")
            horizontal_text = get_text_objects(layout, ltype="horizontal_text")
            vertical_text = get_text_objects(layout, ltype="vertical_text")
            rotation = get_rotation(chars, horizontal_text, vertical_text)
            if rotation != "":
                fpath_new = "".join([froot.replace("page", "p"), "_rotated", fext])
                os.rename(fpath, fpath_new)
                instream = open(fpath_new, "rb")
                infile = PdfFileReader(instream, strict=False)
                if infile.isEncrypted:
                    infile.decrypt(self.password)
                outfile = PdfFileWriter()
                p = infile.getPage(0)
                if rotation == "anticlockwise":
                    p.rotateClockwise(90)
                elif rotation == "clockwise":
                    p.rotateCounterClockwise(90)
                outfile.addPage(p)
                with open(fpath, "wb") as f:
                    outfile.write(f)
                instream.close()

    def parse(
        self, flavor: str = "lattice", suppress_stdout: bool = False, layout_kwargs: dict = {}, **kwargs
    ):
        """Extracts tables by calling parser.get_tables on all single
        page PDFs.

        Parameters
        ----------
        flavor : str (default: 'lattice')
            The parsing method to use ('lattice' or 'stream').
            Lattice is used by default.
        suppress_stdout : str (default: False)
            Suppress logs and warnings.
        layout_kwargs : dict, optional (default: {})
            A dict of `pdfminer.layout.LAParams <https://github.com/euske/pdfminer/blob/master/pdfminer/layout.py#L33>`_ kwargs.
        kwargs : dict
            See camelot.read_pdf kwargs.

        Returns
        -------
        tables : camelot.core.TableList
            List of tables found in PDF.

        """
        tables = []
        with TemporaryDirectory() as tempdir:
            page_info = self._check_page_data(flavor, kwargs, tempdir)
            for i, p in enumerate(page_info):
                if p["file_required"]:
                    self._save_page(self.filepath, p["page"], tempdir)
            parser = Lattice(**kwargs) if flavor == "lattice" else Stream(**kwargs)
            for p in page_info:
                t = parser.extract_tables(
                    p, suppress_stdout=suppress_stdout, layout_kwargs=layout_kwargs
                )
                tables.extend(t)
        return TableList(sorted(tables))

    def _check_page_data(self, flavor: str, kwargs: dict, tempdir: str) -> List[dict]:
        result = []
        pdf_layouts = kwargs.get("pdf_layouts", {})
        pdf_sizes = kwargs.get("pdf_sizes", {})
        pdf_images = kwargs.get("pdf_images", {})
        check_image = flavor == "lattice"

        for page in self.pages:
            page_info: dict = {
                "page": page,
                "layout": pdf_layouts.get(page, None),
                "size": pdf_sizes.get(page, None),
                "image": pdf_images.get(page, None),
                "file": os.path.join(tempdir, f"page-{page}.pdf"),
                "file_required": False
            }
            if page not in pdf_layouts or page not in pdf_sizes:
                page_info["file_required"] = True
            elif check_image and page not in pdf_images:
                page_info["file_required"] = True
            result.append(page_info)

        return result
