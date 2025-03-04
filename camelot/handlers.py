# -*- coding: utf-8 -*-

import os
import sys
from typing import Dict, List, Any

from PyPDF2 import PdfFileReader, PdfFileWriter

from .core import TableList
from .parsers import Stream, Lattice
from .utils import (
    TemporaryDirectory,
    get_page_layout,
    get_char_and_text_objects,
    get_rotation,
    is_url,
    download_url,
)


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

        if pages == "1":
            page_numbers.append({"start": 1, "end": 1})
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

    def _save_page(self, filepath, page, temp, layout_kwargs={}):
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
            layout, dimensions = get_page_layout(fpath, **layout_kwargs)
            chars, horizontal_text, vertical_text = get_char_and_text_objects(layout)
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
        return {"layout": layout, "dimensions": dimensions}

    def parse(
        self, flavor="lattice", suppress_stdout=False, layout_kwargs={}, **kwargs
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

            page_layouts: List[Dict[str, Any]] = []
            for p in self.pages:
                page_layout_per_page = self._save_page(self.filepath, p, tempdir, layout_kwargs)
                page_layouts.append(page_layout_per_page)

            pages = [os.path.join(tempdir, f"page-{p}.pdf") for p in self.pages]
            parser = Lattice(**kwargs) if flavor == "lattice" else Stream(**kwargs)

            for p, page_layout_per_page in zip(pages, page_layouts):
                t = parser.extract_tables(
                    p, page_layout_per_page,
                    suppress_stdout=suppress_stdout, layout_kwargs=layout_kwargs
                )
                tables.extend(t)
        return TableList(sorted(tables))
