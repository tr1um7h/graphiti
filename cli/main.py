import argparse
import asyncio
import sys


def main():
    parser = argparse.ArgumentParser(
        prog='graphiti-cli', description='Graphiti data management CLI'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Export subcommand
    export_parser = subparsers.add_parser('export', help='Export group data to JSONL')
    export_parser.add_argument('--dsn', required=True, help='PostgreSQL DSN')
    export_parser.add_argument('--schema', required=True, help='PostgreSQL schema')
    export_parser.add_argument('--group-id', required=True, help='Group ID to export')
    export_parser.add_argument('--output-dir', required=True, help='Output directory')

    # Import subcommand
    import_parser = subparsers.add_parser('import', help='Import JSONL to database')
    import_parser.add_argument('--dsn', required=True, help='PostgreSQL DSN')
    import_parser.add_argument('--schema', required=True, help='PostgreSQL schema')
    import_parser.add_argument('--input-dir', required=True, help='Input directory')
    import_parser.add_argument('--new-group-id', required=True, help='New group ID')
    import_parser.add_argument('--overwrite', action='store_true', help='Overwrite existing group')

    # Diff subcommand
    diff_parser = subparsers.add_parser('diff', help='Compare two exports')
    diff_parser.add_argument('--left-dir', required=True, help='Left export directory')
    diff_parser.add_argument('--right-dir', required=True, help='Right export directory')
    diff_parser.add_argument('--output', required=True, help='Output patch file')
    diff_parser.add_argument('--html-output', help='HTML report output')

    # Apply subcommand
    apply_parser = subparsers.add_parser('apply', help='Apply patch to database')
    apply_parser.add_argument('--dsn', required=True, help='PostgreSQL DSN')
    apply_parser.add_argument('--schema', required=True, help='PostgreSQL schema')
    apply_parser.add_argument('--patch-file', required=True, help='Patch file path')
    apply_parser.add_argument('--from-group-id', required=True, help='Source group ID')
    apply_parser.add_argument('--to-group-id', required=True, help='Target group ID')
    apply_parser.add_argument(
        '--strategy',
        choices=['ours', 'theirs', 'interactive', 'skip-conflicts'],
        default='ours',
        help='Conflict resolution',
    )
    apply_parser.add_argument('--dry-run', action='store_true', help='Validate without applying')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Run async handler
    asyncio.run(handle_command(args))


async def handle_command(args):
    """Dispatch to command handler."""
    if args.command == 'export':
        print('Export command not yet implemented')
        sys.exit(1)
    elif args.command == 'import':
        print('Import command not yet implemented')
        sys.exit(1)
    elif args.command == 'diff':
        print('Diff command not yet implemented')
        sys.exit(1)
    elif args.command == 'apply':
        print('Apply command not yet implemented')
        sys.exit(1)


if __name__ == '__main__':
    main()
