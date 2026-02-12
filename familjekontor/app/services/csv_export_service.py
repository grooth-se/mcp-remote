"""Generic CSV export helper with UTF-8 BOM for Excel compatibility."""
import csv
import io


def export_csv(rows, columns):
    """Export rows to a BytesIO CSV with UTF-8 BOM.

    Args:
        rows: iterable of dicts (or objects with attributes matching column keys)
        columns: list of (key, header_label) tuples

    Returns:
        io.BytesIO ready for send_file
    """
    si = io.StringIO()
    writer = csv.writer(si, delimiter=';')

    # Header row
    writer.writerow([label for _, label in columns])

    # Data rows
    for row in rows:
        values = []
        for key, _ in columns:
            if isinstance(row, dict):
                val = row.get(key, '')
            else:
                val = getattr(row, key, '')
            if val is None:
                val = ''
            values.append(str(val))
        writer.writerow(values)

    output = io.BytesIO()
    # UTF-8 BOM so Excel opens with correct encoding
    output.write(b'\xef\xbb\xbf')
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    return output
