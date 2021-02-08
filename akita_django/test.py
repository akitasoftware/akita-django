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
import time

from .har import *
from django.core.handlers.wsgi import WSGIRequest
from django.test import Client as DjangoClient
from urllib import parse


class Client(DjangoClient):
    """
    A wrapper around django.test.Client, which logs requests and responses to
    a HAR file.
    """

    def __init__(self, *args, har_file_path=f'akita_trace_{time.time()}.har', **kwargs):
        super().__init__(*args, **kwargs)
        self.har_writer = HarWriter(har_file_path, 'w')

    def request(self, **request):
        start = datetime.datetime.now(datetime.timezone.utc)
        response = super().request(**copy.deepcopy(request))
        self.har_writer.write_entry(self._entry_of_wsgi(start, request, response))

        return response

    def close(self):
        self.har_writer.close()

    def _entry_of_wsgi(self, start: datetime, request, response) -> Entry:
        wsgi = WSGIRequest(self._base_environ(**request))

        # Build request
        server_protocol = 'HTTP/1.1'
        if 'SERVER_PROTOCOL' in wsgi.environ:
            server_protocol = wsgi.environ['SERVER_PROTOCOL']

        url = parse.urlsplit(wsgi.get_raw_uri())
        query_string = [Record(name=k, value=v) for k, v in parse.parse_qs(url.query).items()]

        headers = [Record(name=k, value=v) for k, v in wsgi.headers.items()]
        encoded_headers = '\n'.join([f'{k}: {v}' for k, v in wsgi.headers.items()]).encode("utf-8")
        body = wsgi.body.decode("utf-8")

        har_request = Request(
            method=wsgi.method,
            url=url.path,
            httpVersion=server_protocol,
            cookies=[Record(name=k, value=v) for k, v in wsgi.COOKIES.items()],
            headers=headers,
            queryString=query_string,
            postData=None if not body else PostData(mimeType=wsgi.content_type, text=body),
            headersSize=len(encoded_headers),
            bodySize=len(wsgi.body),
        )

        # Build response
        content = response.content.decode("utf-8") if response.content is not None else ''
        headers = {}
        serialized_headers = response.serialize_headers()
        for x in serialized_headers.decode("utf-8").split('\r\n'):
            kv = x.split(':')
            headers[kv[0].strip()] = kv[1].strip()
        har_response = Response(
            status=response.status_code,
            statusText=response.reason_phrase,
            httpVersion=server_protocol,
            cookies=[Record(name=k, value=v.value) for k, v in response.cookies.items()],
            headers=[Record(name=k, value=v) for k, v in headers.items()],
            content=ResponseContent(size=len(content), mimeType=response.get('Content-Type', ''), text=content),
            redirectURL=response.url if 'url' in dir(response) else '',
            headersSize=len(serialized_headers),
            bodySize=len(response.content),
        )

        return Entry(
            startedDateTime=start,
            time=(datetime.datetime.now(datetime.timezone.utc) - start).total_seconds(),
            request=har_request,
            response=har_response,
            cache=Cache(),
            timings=Timings(send=0, wait=0, receive=0),
        )
