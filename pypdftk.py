# -*- encoding: UTF-8 -*-

''' pypdftk

Python module to drive the awesome pdftk binary.
See http://www.pdflabs.com/tools/pdftk-the-pdf-toolkit/

'''

import logging
import os
import subprocess
import tempfile
import shutil
import fdfgen
from collections import OrderedDict

log = logging.getLogger(__name__)
RADIO_FLAG = 0x8000

if os.getenv('PDFTK_PATH'):
    PDFTK_PATH = os.getenv('PDFTK_PATH')
else:
    PDFTK_PATH = '/usr/bin/pdftk'
    if not os.path.isfile(PDFTK_PATH):
        PDFTK_PATH = 'pdftk'


def check_output(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd)
    return output


def run_command(command, shell=False):
    ''' run a system command and yield output '''
    p = check_output(command, shell=shell)
    return p.split('\n')

try:
    run_command([PDFTK_PATH])
except OSError:
    logging.warning('pdftk test call failed (PDFTK_PATH=%r).', PDFTK_PATH)


def get_num_pages(pdf_path):
    ''' return number of pages in a given PDF file '''
    for line in run_command([PDFTK_PATH, pdf_path, 'dump_data']):
        if line.lower().startswith('numberofpages'):
            return int(line.split(':')[1])
    return 0


def force_value(value, field):
    '''
        Given a value and a field force it to be of the correct time.
        The main function is to check the checkboxes given a boolean value.
        By default it looks for variations of "Yes", "True" and "1"
    '''
    if(field["FieldType"] == "Button" and (int(field.get("FieldFlags",0)) & RADIO_FLAG) == 0):
        if(value):
            acceptable_checks = set(["1", "Yes", "True", "YES", "TRUE", "yes", "true"])
            check_values = set(field.get("FieldStateOption", [])) & acceptable_checks
            for any_check_value in check_values:
                return any_check_value
            # None was found, return "Yes" for consistency but
            # there is no way this check box will be checked.
            return "Yes"
        else:
            return "Off"
    if(isinstance(value, bool)):
        # If boolean value, change to Y or N
        if(value == True):
            return "Y"
        if(value == False):
            return "N"
    return value


def fill_form(pdf_path, datas={}, out_file=None, flatten=True):
    '''
        Fills a PDF form with given dict input data.
        Return temp file if no out_file provided.
    '''
    cleanOnFail = False
    fields = get_dump_data(pdf_path)
    data_cast = datas.copy()
    for k, v in data_cast.iteritems():
        if(k in fields):
            data_cast[k] = force_value(data_cast[k], fields[k])
    tmp_fdf = gen_xfdf(data_cast)
    handle = None
    if not out_file:
        cleanOnFail = True
        handle, out_file = tempfile.mkstemp()

    cmd = "%s %s fill_form %s output %s" % (PDFTK_PATH, pdf_path, tmp_fdf, out_file)
    if flatten:
        cmd += ' flatten'
    try:
        run_command(cmd, True)
    except:
        if cleanOnFail:
            os.remove(tmp_fdf)
        raise
    finally:
        if handle:
            os.close(handle)
    return out_file


def concat(files, out_file=None):
    '''
        Merge multiples PDF files.
        Return temp file if no out_file provided.
    '''
    cleanOnFail = False
    if not out_file:
        cleanOnFail = True
        handle, out_file = tempfile.mkstemp()
    if len(files) == 1:
        shutil.copyfile(files[0], out_file)
    args = [PDFTK_PATH]
    args += files
    args += ['cat', 'output', out_file]
    try:
        run_command(args)
    except:
        if cleanOnFail:
            os.remove(out_file)
        raise
    return out_file


def split(pdf_path, out_dir=None):
    '''
        Split a single PDF file into pages.
        Use a temp directory if no out_dir provided.
    '''
    cleanOnFail = False
    if not out_dir:
        cleanOnFail = True
        out_dir = tempfile.mkdtemp()
    out_pattern = '%s/page_%%02d.pdf' % out_dir
    try:
        run_command((PDFTK_PATH, pdf_path, 'burst', 'output', out_pattern))
    except:
        if cleanOnFail:
            shutil.rmtree(out_dir)
        raise
    out_files = os.listdir(out_dir)
    out_files.sort()
    return [os.path.join(out_dir, filename) for filename in out_files]


def gen_xfdf(datas={}):
    ''' Generates a temp XFDF file suited for fill_form function, based on dict input data '''
    tpl = fdfgen.forge_fdf(None, datas)
    handle, out_file = tempfile.mkstemp()
    f = open(out_file, 'w')
    f.write(tpl)
    f.close()
    return out_file

def replace_page(pdf_path, page_number, pdf_to_insert_path):
    '''
    Replace a page in a PDF (pdf_path) by the PDF pointed by pdf_to_insert_path.
    page_number is the number of the page in pdf_path to be replaced. It is 1-based.
    '''
    A = 'A=' + pdf_path
    B = 'B=' + pdf_to_insert_path
    lower_bound = 'A1-' + str(page_number - 1)
    upper_bound = 'A' + str(page_number + 1) + '-end'
    output_temp = tempfile.mktemp(suffix='.pdf')
    args = (PDFTK_PATH, A, B, 'cat', lower_bound, 'B', upper_bound, 'output', output_temp)
    run_command(args)
    shutil.copy(output_temp, pdf_path)
    os.remove(output_temp)

def stamp(pdf_path, stamp_pdf_path, output_pdf_path=None):
    '''
    Applies a stamp (from stamp_pdf_path) to the PDF file in pdf_path. Useful for watermark purposes.
    If not output_pdf_path is provided, it returns a temporary file with the result PDF.
    '''
    output = output_pdf_path or tempfile.mktemp(suffix='.pdf')
    args = [PDFTK_PATH, pdf_path, 'multistamp', stamp_pdf_path, 'output', output]
    run_command(args)
    return output

def get_fields(pdf_path):
    cmd = "%s %s dump_data_fields" % (PDFTK_PATH, pdf_path)
    out = run_command(cmd, True)
    field_data = {}
    for line in out:
        if(line.startswith("---") and field_data):
            yield field_data
            field_data = {}
        elif(not line.startswith("---") and line.strip()):
            (field_prop, value) = line.split(":", 1)
            if(value.strip()):
                if(field_prop in field_data):
                    if(not isinstance(field_data[field_prop], list)):
                        field_data[field_prop] = [field_data[field_prop]]
                    field_data[field_prop].append(value.strip())
                else:
                    field_data[field_prop] = value.strip()
    if(field_data):
        # The last one
        yield field_data


def get_dump_data(pdf_path):
    dump_data = {}
    for field in get_fields(pdf_path):
        field_name = field["FieldName"]
        dump_data[field_name] = field
    return dump_data

def get_fdf(pdf_path):
    '''
    Get a list of fdf form fields in PDF file.
    '''
    fdf_fields = OrderedDict()
    for field in get_fields(pdf_path):
        field_name = field["FieldName"]
        field_value = field.get("FieldValue", "")
        fdf_fields[field_name] = field_value
    return fdf_fields


def get_field_types(pdf_path):
    '''
    Get field types for each fillable field.
    '''
    field_types = {}
    for field in get_fields(pdf_path):
        field_name = field["FieldName"]
        field_type = field["FieldType"]
        field_types[field_name] = field_type

    return field_types
