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

log = logging.getLogger(__name__)

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


def force_value(value, field_type):
    if(field_type == "Button"):
        if(value):
            return "Yes"
        else:
            return "No"
    return value


def fill_form(pdf_path, datas={}, out_file=None, flatten=True):
    '''
        Fills a PDF form with given dict input data.
        Return temp file if no out_file provided.
    '''
    cleanOnFail = False
    field_types = get_field_types(pdf_path)
    data_cast = datas.copy()
    for k, v in data_cast.iteritems():
        if(k in field_types):
            data_cast[k] = force_value(data_cast[k], field_types[k])
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
    fields = []
    for key, value in datas.items():
        fields.append(u"""<field name="%s"><value>%s</value></field>""" % (key, value))
    tpl = u"""<?xml version="1.0" encoding="UTF-8"?>
    <xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">
        <fields>
            %s
        </fields>
    </xfdf>""" % "\n".join(fields)
    handle, out_file = tempfile.mkstemp()
    f = open(out_file, 'w')
    f.write(tpl.encode('UTF-8'))
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

def get_fdf(pdf_path):
    '''
    Get a list of fdf form fields in PDF file.
    '''
    cmd = "%s %s dump_data_fields" % (PDFTK_PATH, pdf_path)
    out = run_command(cmd, True)
    fields = []
    for line in out:
        if(line.startswith("FieldName:")):
            fields.append(line.split(":",1)[-1].strip())
    return fields


def get_field_types(pdf_path):
    '''
    Get field types for each fillable field.
    '''
    cmd = "%s %s dump_data_fields" % (PDFTK_PATH, pdf_path)
    out = run_command(cmd, True)
    field_types = {}
    field_name = ""
    field_type = ""
    for line in out:
        if(line.startswith("---")):
            field_name = ""
            field_type = ""
        if(line.startswith("FieldName:")):
            field_name = line.split(":", 1)[-1].strip()
        if(line.startswith("FieldType:")):
            field_type = line.split(":", 1)[-1].strip()
        if(field_type and field_name):
            field_types[field_name] = field_type

    return field_types
