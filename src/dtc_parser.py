import re
import fitz
from fitz.fitz import Document
from typing import List, Optional, Dict
from bs4 import BeautifulSoup


class DtcParser:
    """
    DtcParser class for extracting and parsing Diagnostic Trouble Code (DTC) information from PDF documents.

    Attributes:
        DTC_PATTERN (str): A regular expression pattern for matching DTC codes.
        REGEX_OPTIONAL_NEWLINE (str): A regular expression pattern for optional newlines.
        ESCAPED_SPACE (str): An escaped space character.

    Methods:
        parse_dtc(self, startpage: int, endpage: int, target_dtc: str, next_dtc: Optional[str]) -> List[str]:
            Parses DTC information from specified pages.

    Example:
        fpath = '/path/to/pdf/document.pdf'
        with fitz.open(fpath) as pdf_document:
            dtc_parser = DtcParser(pdf_document)
            sols = dtc_parser.parse_dtc(1, 5, 'DTC 000001.01 — Example DTC',
                                        'DTC 000002.01 — Another DTC')
            print(sols)
    Output:
        {
            "solutions" : [list_of_solutions],
            "solution_names" : [list_of_solution_names]
        }
    """
    NEWLINE = '\n'
    DTC_PATTERN = r'(\w{2,3} ?[A-Z0-9]{6,7}[-\.][A-Z0-9]{1,2}).*'
    REGEX_OPTIONAL_NEWLINE = '[ \n]'
    ESCAPED_SPACE = '\\ '

    def __init__(self, pdf_document: Document):
        self.pdf_document = pdf_document

    def _handle_newlines(self, s) -> Optional[str]:
        return s.replace(self.ESCAPED_SPACE, self.REGEX_OPTIONAL_NEWLINE) if s else None

    def _get_pages_html(self, start, stop) -> str:
        all_html_pages = []
        # increase stop to include the end page and the page after
        stop += 2
        for page_idx in range(start, stop):
            page_html = self.pdf_document.load_page(page_idx).get_text('html')
            all_html_pages.append(page_html)
        return self.NEWLINE.join(all_html_pages)

    import re

    def _extract_html_between_dtc_codes(self, html, target_dtc, next_dtc):
        if not target_dtc:
            return None

        dtc_template = re.compile(self.DTC_PATTERN)

        # Extract the actual code from the DTC name
        target_dtc = dtc_template.search(target_dtc).group(1)

        # If next_dtc is empty, return HTML from target_dtc until the end
        if not next_dtc:
            match_start = re.search(target_dtc, html)
            if not match_start:
                return None
            start_index = match_start.end()
            return html[start_index:]

        # Extract the actual code from the next_dtc name
        next_dtc = dtc_template.search(next_dtc).group(1)

        # Find the start and end matches using the provided regular expressions
        match_start = re.search(target_dtc, html)
        match_end = re.search(next_dtc, html)

        # Return None if either start or end match is not found
        if not match_start or not match_end:
            return None

        # Extract the HTML content between the start and end matches
        start_index = match_start.end()
        end_index = match_end.start()

        if end_index > start_index:
            return html[start_index:end_index]
        else:
            return None

    def _solution_names_from_html(self, html) -> List[str]:
        if not html:  # TODO: Check why html is empty (it shouldnt be)
            return []
        soup = BeautifulSoup(html, 'html.parser')
        extracted_text_list = []
        current_text = ""

        # Flag to check if the current span is part of the streak
        in_streak = False

        for span in soup.find_all('span'):
            if span.text == '•' and span.parent.name == 'b':
                # Start a new streak when a bold span with '&#x2022;' is found
                in_streak = True
                current_text = ""
            elif span.parent and span.parent.name == 'b' and in_streak:
                # Concatenate text from bold spans in the streak
                current_text += span.text + " "
            elif in_streak:
                # End the streak when a non-bold span is encountered
                in_streak = False
                # skip the first letter which is the number
                current_text = current_text[1:].strip()
                extracted_text_list.append(current_text)
        return extracted_text_list

    def _get_pages_blocks(self, start, stop) -> List[str]:
        all_blocks = []
        # increase stop to include the end page and the page after
        stop += 2
        for page_idx in range(start, stop):
            page_blocks = self.pdf_document.load_page(
                page_idx).get_text('blocks')
            page_blocks_txt = [b[4] for b in page_blocks]
            # don't include the footer block
            all_blocks += page_blocks_txt[:-1]
        return all_blocks

    def _filter_dtc_blocks(self, blocks: List[str], target_dtc, next_dtc) -> List[str]:
        target_dtc = self._handle_newlines(re.escape(target_dtc))
        if next_dtc:
            next_dtc = self._handle_newlines(re.escape(next_dtc))

        result = []
        matching_started = False

        for block in blocks:
            if re.search(target_dtc, block):
                # Start capturing strings when the first regex is matched
                matching_started = True
            elif matching_started:
                if not next_dtc:
                    result.append(block)
                elif re.search(next_dtc, block):
                    # Stop capturing strings when the last regex is matched
                    matching_started = False
                    break
                else:
                    result.append(block)

        return result

    def _remove_blocks_before_solutions(self, dtc_blocks: List[str], solution_names: List[str]) -> List[str]:
        if not solution_names:
            return []
        first_solname = solution_names[0]
        regex_pattern = fr"\d+ ?{first_solname}"
        # Find the index of the first string that matches the pattern
        match_index = next((i for i, s in enumerate(
            dtc_blocks) if re.search(regex_pattern, s.replace('\n', ' '))), None)
        # If no match is found, return an empty list
        if match_index is None:
            return []
        # Return the sublist from the matched index to the end of the list
        return dtc_blocks[match_index:]

    def _clean_solutions_from_blocks(self, dtc_blocks: List[str], solution_names: List[str]) -> List[str]:
        """returns the solutions without noise"""
        solutions = []
        solution_blocks = self._remove_blocks_before_solutions(
            dtc_blocks, solution_names)
        for block in solution_blocks:
            # clean newlines
            solution = block.replace('\n', ' ')
            # clean numbered list prefix (number and period)
            solution = re.sub(r'^\d+\.', '', solution)
            # clean ok paragraph in the middle of the block
            solution = re.sub(r'(OK:|NOT OK:)(\n|.)*', '', solution)
            # if the block starts with a number and a solution name, remove it
            solution = re.sub(
                fr'^\d* ?({"|".join(solution_names)})', '', solution)
            # fix leading and trailing spaces
            solution = solution.strip()
            # if the block ends with a bullet remove it
            solution = re.sub(' •$', '', solution)
            # filter out noise
            is_ok_block = (block.startswith(
                'OK') or block.startswith('NOT OK:'))
            is_dot = block.startswith('•')
            is_diagnostics = solution == 'Diagnostics'
            is_page_mark = re.search(
                r' -\d{2}-\d{2}[A-Z]{3}\d{2}-\d+/\d+', solution)
            if not (is_ok_block or is_dot or is_diagnostics or is_page_mark):
                solutions.append(solution)
        return solutions

    def parse_dtc(self, startpage: int, endpage: int, target_dtc: str, next_dtc: Optional[str]) -> Dict[str, List[str]]:
        """
        Parses Diagnostic Trouble Code (DTC) information from specified pages in a PDF document.

        Args:
            startpage (int): The starting page index for extracting DTC information.
            endpage (int): The ending page index for extracting DTC information.
            target_dtc (str): The target DTC code to start extraction.
            next_dtc (Optional[str]): The optional next DTC code to end extraction. If None, extraction continues until the end of the document.

        Returns:
            Dict[str, List[str]]: A dictionary containing parsed DTC information.
                - 'solutions': A list of cleaned solutions related to the specified DTC.
                - 'solution_names': A list of solution names extracted from HTML.

        Example:
            fpath = '/path/to/pdf/document.pdf'
            with fitz.open(fpath) as pdf_document:
                dtc_parser = DtcParser(pdf_document)
                sols = dtc_parser.parse_dtc(1, 5, 'DTC 000001.01 — Example DTC',
                                            'DTC 000002.01 — Another DTC')
                print(sols)
        """
        # solution names
        html = self._get_pages_html(startpage, endpage)
        dtc_html = self._extract_html_between_dtc_codes(
            html, target_dtc, next_dtc)
        solution_names = self._solution_names_from_html(dtc_html)

        # solutions
        blocks = self._get_pages_blocks(startpage, endpage)
        dtc_blocks = self._filter_dtc_blocks(blocks, target_dtc, next_dtc)
        solutions = self._clean_solutions_from_blocks(
            dtc_blocks, solution_names)

        return {'solutions': solutions, 'solution_names': solution_names}


if __name__ == '__main__':
    fpath = '/Users/shaked/Downloads/6M_6R Diagnostic and Test Manuals/TM411919.pdf'
    with fitz.open(fpath) as pdf_document:
        dtc_parser = DtcParser(pdf_document)
        sols = dtc_parser.parse_dtc(170, 170, 'ABV 000629.12 — Control Software, Internal Fault',
                                              'ABV 000841.07 — GPS Lock Fault')
        print(sols)
