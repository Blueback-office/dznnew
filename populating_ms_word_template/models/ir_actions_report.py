# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools
from . import mailmerge.MailMerge as MailMerge
from lxml import etree
import binascii
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from io import BytesIO
from datetime import datetime,date
import logging
import pytz

_logger = logging.getLogger(__name__)
try:
    from num2words import num2words
except ImportError:
    _logger.warning("The num2words python library is not installed, amount-to-text features won't be fully available.")
    num2words = None


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    file_template_data = fields.Binary('File template', attachment=True)
    file_template_name = fields.Char('File template')
    populating_ms_word_template = fields.Boolean('Populating MSWord Template', default=False)

    def _convert_binary_to_doc(self, file_template_data=None, suffix='.docx'):
        fp = tempfile.NamedTemporaryFile(suffix=suffix)
        if file_template_data == None:
            fp.write(binascii.a2b_base64(self.file_template_data))
        else:
            fp.write(binascii.a2b_base64(file_template_data))
        fp.seek(0)
        return fp


    def export_doc_by_template(self, file_template_data=None, suffix='docx', file_name_export='export1', datas={}):
        simple_merge = {}
        populating_tables = {}
        file_template = self._convert_binary_to_doc(file_template_data=file_template_data,suffix=suffix)
        document = MailMerge(file_template.name)
        fields = document.get_merge_fields()

        datetime_utc = pytz.timezone('UTC')


        for field in fields:
            childs = field.split('.')
            if len(childs) == 1:
                value = getattr(datas, childs[0], '')
                if isinstance(value, datetime):
                    value = self._convert_datetime_usertz_to_utctz(value)
                elif isinstance(value, date):
                    value = value.strftime(self.env['res.lang'].search([('code', '=', self.env.user.lang)], limit=1).date_format)
                elif isinstance(value, bool):
                    if value == False:
                        value = ''
                    else:
                        value = str(value)
                else:
                    value = str(value)
                simple_merge[field] = value
            else:
                if childs[0] == 'line':
                    childs.remove(childs[0])
                    key = childs[0]
                    data_array = getattr(datas, key)
                    childs.remove(key)
                    tmp_val = []
                    value_field = {}
                    numerical_order = 0
                    for data in data_array:
                        for child in childs:
                            if child == 'numerical_order':
                                data = numerical_order + 1
                                numerical_order = data
                            elif child == "float_time":
                                hour, minute = divmod(data * 60, 60)
                                x_tmp = "%02d:%02d" % (hour, minute)
                                data = x_tmp
                            else:
                                data = getattr(data, child)

                        if isinstance(data, (float, int)) == False and data == False:
                            data = ''
                        elif type(data) == bool:
                            data = ''
                        elif isinstance(data, datetime):
                            data = self._convert_datetime_usertz_to_utctz(data)
                        elif isinstance(data, date):
                            data = data.strftime(
                                self.env['res.lang'].search([('code', '=', self.env.user.lang)], limit=1).date_format)
                        else:
                            data = str(data)
                        tmp_val.append(data)

                    value_field[field] = tmp_val
                    if key in populating_tables:
                        populating_tables[key].append(value_field)
                    else:
                        tmp_value = []
                        tmp_value.append(value_field)
                        populating_tables[key] = tmp_value
                else:
                    if len(childs) <= 0:
                        continue
                    tmp_logic = childs[len(childs)-1]
                    if tmp_logic == 'sum':
                        data_array = getattr(datas, childs[0])
                        sum = 0
                        for data in data_array:
                            value = getattr(data, childs[1])
                            sum += value
                        simple_merge[field] = str(sum)
                    elif tmp_logic == 'count':
                        data_array = getattr(datas, childs[0])
                        count = len(data_array)
                        simple_merge[field] = str(count)
                    elif tmp_logic == 'sum_number2word':
                        data_array = getattr(datas, childs[0])
                        sum = 0
                        for data in data_array:
                            value = getattr(data, childs[1])
                            sum += value
                        num_to_char = self.num2word(sum)
                        simple_merge[field] = num_to_char
                    else:
                        data = datas
                        for child in childs:
                            data = getattr(data,child)
                        simple_merge[field] = str(data)

        document.merge(**simple_merge)

        for key in populating_tables:
            value = populating_tables[key]
            list = []
            anchor = ''
            number = 0
            if number == 0:
                for k in value[0]:
                    val = value[0][k]
                    number = len(val)
                    break
            for i in range(number):
                dict = {}
                for val in value:
                    for k in val:
                        v = val[k]
                        dict[k] = v[i]
                        if anchor == '':
                            anchor = k
                        break
                list.append(dict)
            document.merge_rows(anchor, list)

        for field in document.get_merge_fields():
            document.merge(**{field: ''})

        mem_zip = BytesIO()
        with ZipFile(mem_zip, 'w', ZIP_DEFLATED) as output:
            for zi in document.zip.filelist:
                if zi in document.parts:
                    xml = etree.tostring(document.parts[zi].getroot())
                    output.writestr(zi.filename, xml)
                elif zi == document._settings_info:
                    xml = etree.tostring(document.settings.getroot())
                    output.writestr(zi.filename, xml)
                else:
                    output.writestr(zi.filename, document.zip.read(zi))

        return mem_zip.getvalue()

    def _get_suffix(self):
        return str(self.file_template_name).split(".")[-1]

    def render_doc_doc(self, res_ids=None, data=None):
        suffix = self._get_suffix()
        docx = self.export_doc_by_template(datas=res_ids[0], file_name_export=self.print_report_name,suffix=suffix)
        return docx, suffix

    def _convert_datetime_usertz_to_utctz(self, value):
        # convert back from user's timezone to UTC
        tz_name = self.env.context.get('tz') or self.env.user.tz
        if tz_name:
            try:
                user_tz = pytz.timezone(tz_name)
                dt = value.astimezone(user_tz)
            except Exception:
                _logger.warn(
                    "Failed to convert the value for a field of the model"
                    " %s back from the user's timezone (%s) to UTC",
                    'ir.actions.report', tz_name,
                    exc_info=True)
        return dt.strftime(self.env['res.lang'].search([('code','=', self.env.user.lang)], limit=1).date_format +" " + self.env['res.lang'].search([('code','=', self.env.user.lang)], limit=1).time_format)

    def num2word(self, amount):
        self.ensure_one()

        def _num2words(number, lang):
            try:
                return num2words(number, lang=lang).title()
            except NotImplementedError:
                return num2words(number, lang='en').title()

        if num2words is None:
            logging.getLogger(__name__).warning("The library 'num2words' is missing, cannot render textual amounts.")
            return ""

        formatted = "%.{0}f".format(0) % amount
        parts = formatted.partition('.')
        integer_value = abs(int(parts[0]))

        lang_code = self.env.context.get('lang') or self.env.user.lang
        amount_words = tools.ustr('{amt_value} {amt_word}').format(
            amt_value=_num2words(integer_value, lang=lang_code),
            amt_word=''
        )
        return amount_words
