# -*- coding: utf-8 -*-
import json
import time
from odoo import http

from odoo.tools.safe_eval import safe_eval
from werkzeug.urls import url_decode
from odoo.http import content_disposition, request, \
    serialize_exception as _serialize_exception

from odoo.tools import html_escape

from odoo.addons.web.controllers.main import ReportController

class ReportControllerInherit(ReportController):

    @http.route([
        '/report/<converter>/<reportname>',
        '/report/<converter>/<reportname>/<docids>',
    ], type='http', auth='user', website=True)
    def report_routes(self, reportname, docids=None, converter=None, **data):
        report = request.env['ir.actions.report']._get_report_from_name(reportname)
        context = dict(request.env.context)

        if converter == 'pdf' and report.populating_ms_word_template:
            if docids:
                docids = [int(i) for i in docids.split(',')]
            if data.get('options'):
                data.update(json.loads(data.pop('options')))
            if data.get('context'):
                # Ignore 'lang' here, because the context in data is the one from the webclient *but* if
                # the user explicitely wants to change the lang, this mechanism overwrites it.
                data['context'] = json.loads(data['context'])
                if data['context'].get('lang'):
                    del data['context']['lang']
                context.update(data['context'])
            datas = request.env[report.model].search([('id', '=', docids[0])])

            docx = report.with_context(context).render_doc_doc(datas, data=data)[0]
            docxhttpheaders = [('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')]
            return request.make_response(docx, headers=docxhttpheaders)
        else:
            return super(ReportControllerInherit, self).report_routes(reportname,docids,converter,**data)

    @http.route(['/report/download'], type='http', auth="user")
    def report_download(self, data, token):
        requestcontent = json.loads(data)
        url, type = requestcontent[0], requestcontent[1]
        try:
            if type in ['qweb-pdf', 'qweb-text']:
                converter = 'pdf' if type == 'qweb-pdf' else 'text'
                extension = 'pdf' if type == 'qweb-pdf' else 'txt'

                pattern = '/report/pdf/' if type == 'qweb-pdf' else '/report/text/'
                reportname = url.split(pattern)[1].split('?')[0]

                docids = None
                if '/' in reportname:
                    reportname, docids = reportname.split('/')

                if docids:
                    # Generic report:
                    response = self.report_routes(reportname, docids=docids, converter=converter)
                else:
                    # Particular report:
                    data = url_decode(url.split('?')[1]).items()  # decoding the args represented in JSON
                    response = self.report_routes(reportname, converter=converter, **dict(data))

                report = request.env['ir.actions.report']._get_report_from_name(reportname)

                if not report.populating_ms_word_template:
                    return super(ReportControllerInherit, self).report_download(data, token)
                extension = 'docx'

                filename = "%s.%s" % (report.name, extension)
                if docids:
                    ids = [int(x) for x in docids.split(",")]
                    obj = request.env[report.model].browse(ids)
                    if report.print_report_name and not len(obj) > 1:
                        report_name = safe_eval(report.print_report_name, {'object': obj, 'time': time})
                        filename = "%s.%s" % (report_name, extension)
                response.headers.add('Content-Disposition', content_disposition(filename))
                response.set_cookie('fileToken', token)
                return response
            else:
                return
        except Exception as e:
            se = _serialize_exception(e)
            error = {
                'code': 200,
                'message': "Odoo Server Error",
                'data': se
            }
            return request.make_response(html_escape(json.dumps(error)))
