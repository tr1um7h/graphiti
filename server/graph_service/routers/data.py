"""Data management routes: export, import, diff, patch operations."""

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse

from graph_service.zep_graphiti import ZepGraphitiDep

# Import CLI modules for data operations
from cli.export import export_group_with_sorting  # type: ignore[import-not-found]
from cli.import_ import import_group  # type: ignore[import-not-found]
from cli.diff import diff_groups  # type: ignore[import-not-found]
from cli.apply import apply_patch  # type: ignore[import-not-found]

router = APIRouter()

# Canonical table names
_ALL_TABLES = [
    'entity_nodes',
    'episodic_nodes',
    'community_nodes',
    'saga_nodes',
    'entity_edges',
    'episodic_edges',
    'community_edges',
    'has_episode_edges',
    'next_episode_edges',
]


def _get_schema(driver: Any) -> str:
    """Get schema from driver (works with PostgresAgeDriver)."""
    # Access via getattr to avoid type checker errors with base class
    return getattr(driver, 'schema', 'public')  # type: ignore[attr-defined]


def _validate_patch_structure(patch: dict) -> None:
    """Validate patch document has required structure."""
    if 'version' not in patch:
        raise HTTPException(status_code=400, detail="Patch missing 'version' field")
    if 'metadata' not in patch or not isinstance(patch['metadata'], dict):
        raise HTTPException(status_code=400, detail="Patch missing 'metadata' field")
    if 'changes' not in patch or not isinstance(patch['changes'], dict):
        raise HTTPException(status_code=400, detail="Patch missing 'changes' field")


@router.get('/data/groups', status_code=status.HTTP_200_OK)
async def get_groups(graphiti: ZepGraphitiDep):
    """
    Get all groups with statistics.

    Returns list of groups with node/edge counts per table.
    """
    try:
        driver = graphiti.driver
        schema = _get_schema(driver)

        groups: dict[str, dict] = {}

        # Query each table for group_id and count
        for table_name in _ALL_TABLES:
            results, _, _ = await driver.execute_query(
                f"SELECT group_id, COUNT(*) as count FROM {schema}.{table_name} GROUP BY group_id"
            )
            for record in results or []:
                gid = record.get('group_id', '')
                if gid not in groups:
                    groups[gid] = {'group_id': gid, 'table_counts': {}}
                groups[gid]['table_counts'][table_name] = record.get('count', 0)

        # Calculate totals and get creation time
        result = []
        for gid, data in groups.items():
            table_counts = data['table_counts']
            node_count = sum(table_counts.get(t, 0) for t in _ALL_TABLES if t.endswith('_nodes'))
            edge_count = sum(table_counts.get(t, 0) for t in _ALL_TABLES if t.endswith('_edges'))

            # Get earliest created_at for this group
            created_at_result, _, _ = await driver.execute_query(
                f"SELECT MIN(created_at) as created_at FROM {schema}.entity_nodes WHERE group_id = %(group_id)s",
                params={'group_id': gid}
            )
            created_at = None
            if created_at_result and created_at_result[0].get('created_at'):
                ca = created_at_result[0]['created_at']
                created_at = ca.isoformat() if hasattr(ca, 'isoformat') else str(ca)

            result.append({
                'group_id': gid,
                'created_at': created_at,
                'node_count': node_count,
                'edge_count': edge_count,
                'table_counts': table_counts,
            })

        return result
    except Exception as e:
        import traceback
        print(f'❌ Error in get_groups: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/data/groups/{group_id}', status_code=status.HTTP_200_OK)
async def get_group_detail(group_id: str, table: str | None = None, page: int = 1, size: int = 100, graphiti: ZepGraphitiDep = ...):  # type: ignore[assignment]
    """
    Get group details with optional table data pagination.

    If table is specified, returns paginated records from that table.
    """
    try:
        driver = graphiti.driver
        schema = _get_schema(driver)

        # Get table counts for this group
        table_counts = {}
        for table_name in _ALL_TABLES:
            count_result, _, _ = await driver.execute_query(
                f"SELECT COUNT(*) as count FROM {schema}.{table_name} WHERE group_id = %(group_id)s",
                params={'group_id': group_id}
            )
            table_counts[table_name] = count_result[0].get('count', 0) if count_result else 0

        total_records = sum(table_counts.values())
        if total_records == 0:
            raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found or empty")

        # If specific table requested, return paginated data
        records = []
        total = 0
        if table:
            if table not in _ALL_TABLES:
                raise HTTPException(status_code=400, detail=f"Invalid table name: {table}")

            total = table_counts.get(table, 0)
            offset = (page - 1) * size

            query_result, _, _ = await driver.execute_query(
                f"SELECT * FROM {schema}.{table} WHERE group_id = %(group_id)s ORDER BY created_at DESC OFFSET %(offset)s LIMIT %(limit)s",
                params={'group_id': group_id, 'offset': offset, 'limit': size}
            )

            # Convert datetime objects to ISO strings
            for record in query_result or []:
                row = {}
                for k, v in record.items():
                    if hasattr(v, 'isoformat'):
                        row[k] = v.isoformat()
                    else:
                        row[k] = v
                records.append(row)

        return {
            'group_id': group_id,
            'table': table,
            'page': page,
            'size': size,
            'total': total,
            'table_counts': table_counts,
            'records': records,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f'❌ Error in get_group_detail: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/data/groups/{group_id}/export', status_code=status.HTTP_200_OK)
async def export_group(group_id: str, graphiti: ZepGraphitiDep):
    """
    Export group data as ZIP file containing JSONL files.

    Returns a ZIP file with metadata.json and JSONL files for each table.
    """
    try:
        driver = graphiti.driver
        schema = _get_schema(driver)

        # Verify group exists
        check_result, _, _ = await driver.execute_query(
            f"SELECT COUNT(*) as count FROM {schema}.entity_nodes WHERE group_id = %(group_id)s",
            params={'group_id': group_id}
        )
        if not check_result or check_result[0].get('count', 0) == 0:
            raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

        # Create temp directory for export
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / 'export'
            await export_group_with_sorting(driver, group_id, schema, output_dir)

            # Create ZIP in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in output_dir.iterdir():
                    zf.write(file_path, file_path.name)

            zip_buffer.seek(0)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            filename = f"{group_id}_export_{timestamp}.zip"

            return StreamingResponse(
                zip_buffer,
                media_type='application/zip',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f'❌ Error in export_group: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/data/import', status_code=status.HTTP_201_CREATED)
async def import_data(
    file: UploadFile = File(...),
    new_group_id: str = Form(...),
    overwrite: bool = Form(False),
    graphiti: ZepGraphitiDep = ...,  # type: ignore[assignment]
):
    """
    Import data from ZIP file.

    Creates a new group with the specified group_id from the uploaded JSONL export.
    """
    try:
        if not file.filename or not file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="File must be a ZIP archive")

        driver = graphiti.driver

        # Read uploaded file into memory
        content = await file.read()
        zip_buffer = BytesIO(content)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / 'import'
            input_dir.mkdir()

            # Extract ZIP
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                zf.extractall(input_dir)

            # Verify metadata.json exists
            metadata_path = input_dir / 'metadata.json'
            if not metadata_path.exists():
                raise HTTPException(status_code=400, detail="ZIP must contain metadata.json")

            # Import data
            await import_group(driver, input_dir, new_group_id, overwrite)

            # Query table counts for the newly imported group
            schema = _get_schema(driver)
            table_counts = {}
            for table_name in _ALL_TABLES:
                count_result, _, _ = await driver.execute_query(
                    f"SELECT COUNT(*) as count FROM {schema}.{table_name} WHERE group_id = %(group_id)s",
                    params={'group_id': new_group_id}
                )
                table_counts[table_name] = count_result[0].get('count', 0) if count_result else 0

            return {
                'success': True,
                'group_id': new_group_id,
                'message': 'Imported successfully',
                'table_counts': table_counts,
            }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        import traceback
        print(f'❌ Error in import_data: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/data/diff', status_code=status.HTTP_200_OK)
async def get_diff(left: str, right: str, graphiti: ZepGraphitiDep):
    """
    Generate diff between two groups.

    Returns a patch document describing the differences.
    """
    try:
        driver = graphiti.driver
        schema = _get_schema(driver)

        # Verify both groups exist
        for group_id in [left, right]:
            check_result, _, _ = await driver.execute_query(
                f"SELECT COUNT(*) as count FROM {schema}.entity_nodes WHERE group_id = %(group_id)s",
                params={'group_id': group_id}
            )
            if not check_result or check_result[0].get('count', 0) == 0:
                raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

        # Export both groups to temp directories
        with tempfile.TemporaryDirectory() as tmpdir:
            left_dir = Path(tmpdir) / 'left'
            right_dir = Path(tmpdir) / 'right'

            await export_group_with_sorting(driver, left, schema, left_dir)
            await export_group_with_sorting(driver, right, schema, right_dir)

            # Generate diff
            patch = diff_groups(left_dir, right_dir)

            return patch
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f'❌ Error in get_diff: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/data/diff/export', status_code=status.HTTP_200_OK)
async def export_diff(left: str, right: str, graphiti: ZepGraphitiDep):
    """
    Export diff between two groups as JSON file.

    Returns a JSON patch file.
    """
    try:
        driver = graphiti.driver
        schema = _get_schema(driver)

        # Verify both groups exist
        for group_id in [left, right]:
            check_result, _, _ = await driver.execute_query(
                f"SELECT COUNT(*) as count FROM {schema}.entity_nodes WHERE group_id = %(group_id)s",
                params={'group_id': group_id}
            )
            if not check_result or check_result[0].get('count', 0) == 0:
                raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

        # Export both groups to temp directories
        with tempfile.TemporaryDirectory() as tmpdir:
            left_dir = Path(tmpdir) / 'left'
            right_dir = Path(tmpdir) / 'right'

            await export_group_with_sorting(driver, left, schema, left_dir)
            await export_group_with_sorting(driver, right, schema, right_dir)

            # Generate diff
            patch = diff_groups(left_dir, right_dir)

            # Return as JSON download
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            filename = f"diff_{left}_vs_{right}_{timestamp}.json"

            return JSONResponse(
                content=patch,
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f'❌ Error in export_diff: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/data/patch/preview', status_code=status.HTTP_200_OK)
async def preview_patch(file: UploadFile = File(...)):
    """
    Preview a patch file.

    Returns summary statistics without the full patch content.
    """
    try:
        if not file.filename or not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail="File must be a JSON file")

        content = await file.read()
        try:
            patch = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

        # Validate patch structure
        _validate_patch_structure(patch)

        # Build summary (counts only, no full patch content)
        summary = {}
        for table_name, changes in patch.get('changes', {}).items():
            summary[table_name] = {
                'added': len(changes.get('added', [])),
                'removed': len(changes.get('removed', [])),
                'modified': len(changes.get('modified', [])),
                'conflicts': len(changes.get('conflicts', [])),
            }

        return {
            'version': patch.get('version'),
            'metadata': patch.get('metadata'),
            'summary': summary,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f'❌ Error in preview_patch: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel


class ApplyPatchRequest(BaseModel):
    """Request body for apply patch endpoint."""
    patch: dict
    from_group_id: str | None = None
    to_group_id: str
    strategy: str = 'ours'
    dry_run: bool = False


@router.post('/data/patch/apply', status_code=status.HTTP_200_OK)
async def apply_patch_endpoint(
    request: ApplyPatchRequest,
    graphiti: ZepGraphitiDep = ...,  # type: ignore[assignment]
):
    """
    Apply a patch to a target group.

    Supports strategies: ours, theirs, skip-conflicts.
    """
    try:
        driver = graphiti.driver
        patch = request.patch
        from_group_id = request.from_group_id
        to_group_id = request.to_group_id
        strategy = request.strategy
        dry_run = request.dry_run

        # Validate patch structure
        _validate_patch_structure(patch)

        # Get from_group_id from patch if not provided
        if not from_group_id:
            from_group_id = patch.get('metadata', {}).get('from_group_id')
            if not from_group_id:
                raise HTTPException(status_code=400, detail="from_group_id required")

        # Validate strategy
        if strategy not in ['ours', 'theirs', 'skip-conflicts']:
            raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}")

        # Apply patch
        result = await apply_patch(
            driver, patch, from_group_id, to_group_id, strategy=strategy, dry_run=dry_run
        )

        return {
            'success': True,
            'dry_run': dry_run,
            'added': result.get('added', 0),
            'removed': result.get('removed', 0),
            'modified': result.get('modified', 0),
            'conflicts': result.get('conflicts', 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f'❌ Error in apply_patch_endpoint: {e}', flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
