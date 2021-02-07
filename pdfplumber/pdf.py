from .container import Container
from .page import Page
from .utils import resolve_and_decode

import logging
import pathlib
import itertools
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.layout import LAParams
from pdfminer.converter import PDFPageAggregator

logger = logging.getLogger(__name__)


class PDF(Container):
    cached_properties = Container.cached_properties + ["_pages"]

    def __init__(
        self,
        stream,
        pages=None,
        laparams=None,
        password="",
        strict_metadata=False,
    ):
        self.laparams = None if laparams is None else LAParams(**laparams)
        self.stream = stream
        self.pages_to_parse = pages
        rsrcmgr = PDFResourceManager()
        self.doc = PDFDocument(PDFParser(stream), password=password)
        self.metadata = {}
        for info in self.doc.info:
            self.metadata.update(info)
        for k, v in self.metadata.items():
            try:
                self.metadata[k] = resolve_and_decode(v)
            except Exception as e:
                if strict_metadata:
                    # Raise an exception since unable to resolve the metadata value.
                    raise
                # This metadata value could not be parsed. Instead of failing the PDF
                # read, treat it as a warning only if `strict_metadata=False`.
                logger.warning(
                    f'[WARNING] Metadata key "{k}" could not be parsed due to '
                    f"exception: {str(e)}"
                )
        self.device = PDFPageAggregator(rsrcmgr, laparams=self.laparams)
        self.interpreter = PDFPageInterpreter(rsrcmgr, self.device)

    @classmethod
    def open(cls, path_or_fp, **kwargs):
        if isinstance(path_or_fp, (str, pathlib.Path)):
            fp = open(path_or_fp, "rb")
            inst = cls(fp, **kwargs)
            inst.close = fp.close
            return inst
        else:
            return cls(path_or_fp, **kwargs)

    def process_page(self, page):
        self.interpreter.process_page(page)
        return self.device.get_result()

    @property
    def pages(self):
        if hasattr(self, "_pages"):
            return self._pages

        doctop = 0
        pp = self.pages_to_parse
        self._pages = []
        for i, page in enumerate(PDFPage.create_pages(self.doc)):
            page_number = i + 1
            if pp is not None and page_number not in pp:
                continue
            p = Page(self, page, page_number=page_number, initial_doctop=doctop)
            self._pages.append(p)
            doctop += p.height
        return self._pages

    def close(self):
        """
        Override this method to execute code on __exit__.
        """
        pass

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.flush_cache()
        self.close()

    @property
    def objects(self):
        if hasattr(self, "_objects"):
            return self._objects
        all_objects = {}
        for p in self.pages:
            for kind in p.objects.keys():
                all_objects[kind] = all_objects.get(kind, []) + p.objects[kind]
        self._objects = all_objects
        return self._objects

    @property
    def annots(self):
        gen = (p.annots for p in self.pages)
        return list(itertools.chain(*gen))

    @property
    def hyperlinks(self):
        gen = (p.hyperlinks for p in self.pages)
        return list(itertools.chain(*gen))
