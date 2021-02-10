# 3-Clause BSD License
# 
# Copyright (c) 2009, Boxed Ice <hello@boxedice.com>
# Copyright (c) 2010-2016, Datadog <info@datadoghq.com>
# Copyright (c) 2020-present, Akita Software <info@akitasoftware.com>
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import copy
import datetime
import time

import akita_har.models as M

from akita_har import HarWriter
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.test import Client as DjangoClient
from urllib import parse

from . import __version__


def django_to_har_entry(start: datetime, request: WSGIRequest, response: HttpResponse) -> M.Entry:
    """
    Converts a Django request/response pair to a HAR file entry.
    :param start: The start of the request, which must be timezone-aware.
    :param request: A Django request, as produced by django.test.RequestFactory.
    :param response: The response from your Django service.
    :return: A HAR file entry.
    """
    if start.tzinfo is None:
        raise ValueError('start datetime must be timezone-aware')

    # Build request
    server_protocol = 'HTTP/1.1'
    if 'SERVER_PROTOCOL' in request.environ:
        server_protocol = request.environ['SERVER_PROTOCOL']

    url = parse.urlsplit(request.get_raw_uri())
    query_string = [M.Record(name=k, value=v) for k, v in parse.parse_qs(url.query).items()]

    headers = [M.Record(name=k, value=v) for k, v in request.headers.items()]
    encoded_headers = '\n'.join([f'{k}: {v}' for k, v in request.headers.items()]).encode("utf-8")
    body = request.body.decode("utf-8")

    har_request = M.Request(
        method=request.method,
        url=url.path,
        httpVersion=server_protocol,
        cookies=[M.Record(name=k, value=v) for k, v in request.COOKIES.items()],
        headers=headers,
        queryString=query_string,
        postData=None if not body else M.PostData(mimeType=request.content_type, text=body),
        headersSize=len(encoded_headers),
        bodySize=len(request.body),
    )

    # Build response
    content = response.content.decode("utf-8") if response.content is not None else ''
    headers = {}
    serialized_headers = response.serialize_headers()
    for x in serialized_headers.decode("utf-8").split('\r\n'):
        kv = x.split(':')
        headers[kv[0].strip()] = kv[1].strip()
    har_response = M.Response(
        status=response.status_code,
        statusText=response.reason_phrase,
        httpVersion=server_protocol,
        cookies=[M.Record(name=k, value=v.value) for k, v in response.cookies.items()],
        headers=[M.Record(name=k, value=v) for k, v in headers.items()],
        content=M.ResponseContent(size=len(content), mimeType=response.get('Content-Type', ''), text=content),
        redirectURL=response.url if 'url' in dir(response) else '',
        headersSize=len(serialized_headers),
        bodySize=len(response.content),
    )

    return M.Entry(
        startedDateTime=start,
        time=(datetime.datetime.now(datetime.timezone.utc) - start).total_seconds(),
        request=har_request,
        response=har_response,
        cache=M.Cache(),
        timings=M.Timings(send=0, wait=0, receive=0),
    )


class Client(DjangoClient):
    """
    A wrapper around django.test.Client, which logs requests and responses to
    a HAR file.
    """

    def __init__(self, *args, har_file_path=f'akita_trace_{time.time()}.har', **kwargs):
        super().__init__(*args, **kwargs)
        creator = M.Creator(
            name="Akita DjangoClient",
            version=__version__,
            comment="https://docs.akita.software/docs/integrate-with-django",
        )
        browser = M.Browser(
            name="",
            version="",
        )
        comment = "Created by the Akita DjangoClient."
        self.har_writer = HarWriter(har_file_path, 'w', creator=creator, browser=browser, comment=comment)

    def request(self, **request):
        start = datetime.datetime.now(datetime.timezone.utc)
        wsgi_request = WSGIRequest(self._base_environ(**request))
        response = super().request(**copy.deepcopy(request))
        self.har_writer.write_entry(django_to_har_entry(start, wsgi_request, response))

        return response

    def close(self):
        self.har_writer.close()

