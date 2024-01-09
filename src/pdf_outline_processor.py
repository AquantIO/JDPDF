import PyPDF2
import pandas as pd
import os


class PdfOutlineProcessor:
    """
    A class for processing PDF outlines and creating a hierarchical DataFrame with titles and page numbers.

    Methods:
    - extract_outline(): Get the DataFrame with hierarchical titles and page numbers.

    Attributes:
    - pdf_path (str): The path to the PDF file.
    """

    def __init__(self, pdf_path):
        """
        Initializes the PdfOutlineProcessor object with the path to the PDF file.

        Parameters:
        - pdf_path (str): The path to the PDF file.
        """
        self.pdf_path = pdf_path

    def print_outlines(self, pdf_reader, outlines, indent=0, header_level=0) -> None:
        """
        Print headers with page numbers.

        Parameters:
        - pdf_reader: The PyPDF2 PdfReader object.
        - outlines: The outlines extracted from the PDF.
        - indent (int): The indentation level for printing.
        - header_level (int): The current header level.
        """
        for outline in outlines:
            if isinstance(outline, list):
                self.print_outlines(pdf_reader, outline,
                                    indent + 4, header_level + 1)
            else:
                title = outline.get('/Title')
                if title:
                    asterisks = '*' * (header_level + 1)
                    page_num = pdf_reader.get_destination_page_number(
                        outline) if pdf_reader else None
                    page_info = f" (Page {page_num})" if page_num is not None else ""
                    print(' ' * indent + f"{asterisks} {title}{page_info}")

    def _build_outline_json(self, pdf_reader, outlines, header_level=0):
        """
        Convert outlines to JSON format (list of dictionaries).

        Parameters:
        - pdf_reader: The PyPDF2 PdfReader object.
        - outlines: The outlines extracted from the PDF.
        - header_level (int): The current header level.

        Returns:
        - list: List of dictionaries representing the outlines in JSON format.
        """
        outline_json = []
        pointer = 0
        while pointer < len(outlines):
            page_num = pdf_reader.get_destination_page_number(
                outlines[pointer]) if pdf_reader else None
            if pointer + 1 < len(outlines) and isinstance(outlines[pointer + 1], list):
                outline_dict = {
                    "title": outlines[pointer].get('/Title'),
                    "header_level": header_level + 1,
                    "sub_headers": self._build_outline_json(pdf_reader, outlines[pointer + 1], header_level + 1),
                    "page_num": page_num
                }
                outline_json.append(outline_dict)
                pointer += 2
            else:
                title = outlines[pointer].get('/Title')
                if title:
                    page_info = f"Page {page_num}" if page_num is not None else ""
                    outline_dict = {
                        "title": title,
                        "header_level": header_level + 1,
                        "page_info": page_info,
                        "page_num": page_num
                    }
                    outline_json.append(outline_dict)
                pointer += 1
        return outline_json

    def _get_max_header_level(self, titles):
        """
        Get the maximum header level for creating the DataFrame.

        Parameters:
        - titles (list): List of title dictionaries.

        Returns:
        - int: Maximum header level.
        """
        max_header_level = 0
        for title in titles:
            max_header_level = max(max_header_level, title.get('header_level'))
            if title.get('sub_headers'):
                max_header_level = max(
                    max_header_level, self._get_max_header_level(title.get('sub_headers')))
        return max_header_level

    def _create_title_row(self, title, max_header_level, prevLevels=[]):
        """
        Create a row for the DataFrame with title and page number.

        Parameters:
        - title (dict): Title dictionary.
        - max_header_level (int): Maximum header level for DataFrame columns.
        - prevLevels (list): Previous header levels.

        Returns:
        - pd.DataFrame: DataFrame row with title and page number.
        """
        title_row = []
        title_row += prevLevels
        title_row += [title.get('title')] + [""] * (max_header_level - len(prevLevels) - 1) + [title.get('page_num')]  # noqa E501
        return pd.DataFrame([title_row], columns=[f"H{i}" for i in range(1, max_header_level + 1)] + ['page_num'])

    def _create_titles_dataframe(self, titles, prevLevels=[], max_header_level=None):
        """
        Create a DataFrame from the JSON outlines.

        Parameters:
        - titles (list): List of title dictionaries.
        - prevLevels (list): Previous header levels.
        - max_header_level (int): Maximum header level for DataFrame columns.

        Returns:
        - pd.DataFrame: DataFrame with hierarchical titles and page numbers.
        """
        if max_header_level is None:
            max_header_level = self._get_max_header_level(titles)
        titles_df = pd.DataFrame(
            columns=[f"H{i}" for i in range(1, max_header_level + 1)] + ['page_num'])
        for title in titles:
            titles_df = pd.concat(
                [titles_df, self._create_title_row(title, max_header_level, prevLevels)])
            if type(title.get('sub_headers')) == list:
                titles_df = pd.concat([titles_df,
                                       self._create_titles_dataframe(title.get('sub_headers'), prevLevels + [title.get('title')],
                                                                     max_header_level)])
        return titles_df

    def extract_outline(self) -> pd.DataFrame:
        """
        Get the DataFrame with hierarchical titles and page numbers.

        Returns:
        - pd.DataFrame: DataFrame with hierarchical titles and page numbers.

        Reamrk: Page Numbers are zero based.
        """
        with open(self.pdf_path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            outlines = pdf_reader.outline
            if outlines:
                result = self._build_outline_json(
                    pdf_reader, outlines, header_level=0)
                return self._create_titles_dataframe(result)
            else:
                print("No outlines found in the PDF.")


if __name__ == '__main__':
    fpath = '/Users/shaked/Downloads/6M_6R Diagnostic and Test Manuals/TM410319.pdf'
    pdfprocessor = PdfOutlineProcessor(fpath)
    titles_df = pdfprocessor.extract_outline()
    titles_df['pdf_file_name'] = os.path.basename(fpath)
    dtc_mask = (titles_df['H2'] == 'Diagnostic Trouble Codes') & (
        titles_df['H4'.notna()])
    titles_df = titles_df[dtc_mask].drop(columns='H5').drop_duplicates()
    titles_df['next_section_page_num'] = titles_df['page_num'].shift(-1)
    titles_df.to_csv(os.path.join('/users/shaked/Downloads', 'titles_df.csv'),
                     index=False, encoding='utf-8-sig')
