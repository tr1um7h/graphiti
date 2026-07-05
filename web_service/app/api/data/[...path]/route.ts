// app/api/data/[...path]/route.ts
// Proxy all /api/data/* requests to Python backend /rest/data/*

import { NextRequest, NextResponse } from 'next/server';

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(req: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const backendPath = `/rest/data/${path.join('/')}`;
  const url = `${PYTHON_API_URL}${backendPath}${req.nextUrl.search}`;

  try {
    const headers: Record<string, string> = {};
    const contentType = req.headers.get('content-type');
    if (contentType) {
      headers['Content-Type'] = contentType;
    }

    const fetchOptions: RequestInit = {
      method: req.method,
      headers,
    };

    // For POST/PUT/PATCH, forward the body
    if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
      if (contentType?.includes('multipart/form-data')) {
        // For multipart, forward the raw body
        fetchOptions.body = await req.arrayBuffer();
      } else {
        // For JSON, forward as JSON
        fetchOptions.body = await req.text();
      }
    }

    const res = await fetch(url, fetchOptions);

    // Handle file downloads (ZIP, JSON)
    const responseContentType = res.headers.get('content-type') || '';
    if (
      responseContentType.includes('application/zip') ||
      responseContentType.includes('application/json')
    ) {
      const contentDisposition = res.headers.get('content-disposition');
      const responseHeaders: Record<string, string> = {
        'Content-Type': responseContentType,
      };
      if (contentDisposition) {
        responseHeaders['Content-Disposition'] = contentDisposition;
      }

      const buffer = await res.arrayBuffer();
      return new NextResponse(buffer, {
        status: res.status,
        headers: responseHeaders,
      });
    }

    // For regular JSON responses
    if (!res.ok) {
      const error = await res.json().catch(() => ({ error: 'Backend error' }));
      return NextResponse.json(error, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Data API proxy error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Proxy error' },
      { status: 500 }
    );
  }
}

export async function GET(req: NextRequest, context: RouteContext) {
  return proxyRequest(req, context);
}

export async function POST(req: NextRequest, context: RouteContext) {
  return proxyRequest(req, context);
}
