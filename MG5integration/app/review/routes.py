from flask import render_template, request, abort

from app.review import review_bp
from app.services.review_service import (
    get_overall_summary, get_table_data, TABLE_REGISTRY,
)


@review_bp.route('/')
def summary():
    data = get_overall_summary()
    return render_template('review/summary.html', **data)


@review_bp.route('/table/<table_key>')
def table_detail(table_key):
    if table_key not in TABLE_REGISTRY:
        abort(404)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    per_page = min(per_page, 100)
    search = request.args.get('search', '').strip() or None
    sort_by = request.args.get('sort_by', None)
    sort_dir = request.args.get('sort_dir', 'asc')
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'

    data = get_table_data(table_key, page, per_page, search, sort_by, sort_dir)
    if data is None:
        abort(404)

    info = TABLE_REGISTRY[table_key]
    return render_template(
        'review/table_detail.html',
        table_key=table_key,
        label=info['label'],
        columns=data['columns'],
        rows=data['rows'],
        pagination=data['pagination'],
        search=search or '',
        sort_by=sort_by or info['default_sort'],
        sort_dir=sort_dir,
        per_page=per_page,
        required_fields=info['required'],
        amount_fields=info['amounts'],
    )
