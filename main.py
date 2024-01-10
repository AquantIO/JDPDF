from src.dtc_parser import DtcParser
from src.pdf_outline_processor import PdfOutlineProcessor
import os
import fitz
import pandas as pd
import numpy as np
import glob

TARGET_COLUMNS = ['pdf_file', 'Title1',
                  'Title2 (Section)', 'Title3 (Observation Name)', 'Title4 (Solution Name)', 'Title5 (Solution Name)']


def create_pdf_outline(file: str) -> pd.DataFrame:
    pdfprocessor = PdfOutlineProcessor(file)
    titles_df = pdfprocessor.extract_outline()
    # add columns
    dtc_mask = (titles_df['H2'].isin(['Diagnostic Trouble Codes', 'Diagnostic Service Codes'])) & (
        titles_df['H4'] != '')
    titles_df['pdf_file_name'] = os.path.basename(file)
    titles_df['next_section_page_num'] = titles_df['page_num'].shift(-1)
    titles_df = titles_df[dtc_mask]
    titles_df = (
        titles_df
        .drop(columns='H5')
        .drop_duplicates(subset=['H4'], keep='first')
    )
    titles_df['next_H4'] = titles_df['H4'].shift(-1)
    return titles_df


if __name__ == '__main__':
    results = pd.DataFrame(columns=TARGET_COLUMNS)

    for fpath in glob.glob('/Users/shaked/Downloads/6M_6R Diagnostic and Test Manuals/*.pdf'):
        print(f'processing pdf file {fpath}...')

        titles_df = create_pdf_outline(fpath)

        with fitz.open(fpath) as pdf_document:
            # initialize parser
            dtcparser = DtcParser(pdf_document)

            # iterate titles df
            for _, row in titles_df.iterrows():
                pagenum = row['page_num']
                next_pagenum = row['next_section_page_num']
                target_dtc = row['H4'].strip()
                next_dtc = row['next_H4'].strip() if row['next_H4'] else None
                filename = row['pdf_file_name']
                h2 = row['H2']
                h3 = row['H3']

                extracted = dtcparser.parse_dtc(pagenum,
                                                next_pagenum,
                                                target_dtc,
                                                next_dtc)
                solutions = extracted.get('solutions')
                solution_names = extracted.get('solution_names')

                solname_records = [(filename, h2, h3, target_dtc, solname, np.nan)
                                   for solname in solution_names]
                sol_records = [(filename, h2, h3, target_dtc, np.nan, sol)
                               for sol in solutions]
                all_records = solname_records + sol_records
                dtc_data = pd.DataFrame(all_records, columns=TARGET_COLUMNS)
                results = pd.concat([results, dtc_data], ignore_index=True)

    results.to_csv('/users/shaked/downloads/test.csv',
                   index=False, encoding='utf-8-sig')
