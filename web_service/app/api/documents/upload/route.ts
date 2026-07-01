import { fetchFromBackend } from '@/lib/api-client';

export async function POST(request: Request) {
  const contentType = request.headers.get('content-type') || '';

  // URL import (JSON body with { url })
  if (contentType.includes('application/json')) {
    const body = await request.json();
    const url = (body as { url?: string; group_id?: string }).url;
    const groupId = (body as { group_id?: string }).group_id || 'default';
    if (!url) {
      return Response.json({ error: 'No URL provided' }, { status: 400 });
    }
    try {
      const messagesRequest = {
        group_id: groupId,
        messages: [
          {
            uuid: `doc-${Date.now()}-${url}`,
            name: `Document: ${url}`,
            role: 'user',
            role_type: 'user',
            content: url,
            timestamp: new Date().toISOString(),
            source_description: `Imported URL: ${url}`,
          },
        ],
      };
      await fetchFromBackend<{ message: string; success: boolean }>({
        path: '/messages',
        method: 'POST',
        body: JSON.stringify(messagesRequest),
      });
      return Response.json({
        success: true,
        name: url,
        group_id: groupId,
      });
    } catch (error) {
      console.error('URL import error:', error);
      return Response.json(
        { error: error instanceof Error ? error.message : 'Import failed' },
        { status: 500 },
      );
    }
  }

  // File upload (multipart/form-data) - 读取文件内容并调用 REST API /messages 接口
  const formData = await request.formData();
  const file = formData.get('file') as File | null;
  const groupId = (formData.get('group_id') as string) || 'default';

  if (!file) {
    return Response.json({ error: 'No file provided' }, { status: 400 });
  }

  try {
    // 1. 读取文件内容
    const fileContent = await file.text();
    const fileName = file.name;

    // 2. 构造消息请求体
    const messagesRequest = {
      group_id: groupId,
      messages: [
        {
          uuid: `doc-${Date.now()}-${fileName}`,
          name: `Document: ${fileName}`,
          role: 'user',
          role_type: 'user',
          content: fileContent,
          timestamp: new Date().toISOString(),
          source_description: `Uploaded file: ${fileName}`,
        },
      ],
    };

    // 3. 调用 REST API /messages 接口
    await fetchFromBackend<{ message: string; success: boolean }>({
      path: '/messages',
      method: 'POST',
      body: JSON.stringify(messagesRequest),
    });

    return Response.json({
      success: true,
      message: `File '${fileName}' uploaded and queued for processing`,
      document_id: messagesRequest.messages[0].uuid,
      group_id: groupId,
    });
  } catch (error) {
    console.error('Upload error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Upload failed' },
      { status: 500 },
    );
  }
}
