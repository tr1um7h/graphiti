import { NextResponse } from 'next/server';

interface SchemaResponse {
  nodeLabels: { label: string; count: number }[];
  relationshipTypes: { type: string; count: number }[];
}

// Mock schema data — replace with fetchFromBackend('/graph/schema') when backend is ready
const mockSchema: SchemaResponse = {
  nodeLabels: [
    { label: 'Person', count: 556 },
    { label: 'Company', count: 247 },
    { label: 'Project', count: 185 },
    { label: 'Organization', count: 124 },
    { label: 'Fund', count: 62 },
    { label: 'Product', count: 38 },
    { label: 'Technology', count: 22 },
  ],
  relationshipTypes: [
    { type: 'RELATED_TO', count: 1200 },
    { type: 'WORKS_AT', count: 567 },
    { type: 'INVESTED_IN', count: 434 },
    { type: 'PARTICIPATED_IN', count: 289 },
    { type: 'MEMBER_OF', count: 212 },
    { type: 'CREATED_BY', count: 178 },
    { type: 'LOCATED_IN', count: 145 },
    { type: 'OWNS', count: 112 },
  ],
};

export async function GET() {
  try {
    // TODO: const data = await fetchFromBackend<SchemaResponse>('/graph/schema');
    return NextResponse.json(mockSchema);
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to fetch graph schema' },
      { status: 500 }
    );
  }
}
