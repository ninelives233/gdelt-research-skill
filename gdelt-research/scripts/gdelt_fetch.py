#!/usr/bin/env python3
"""Small, auditable GDELT downloader. Python 3.10+, curl; no pip dependencies."""
import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

UTC = timezone.utc
DOC = 'https://api.gdeltproject.org/api/v2/doc/doc'
DATA = 'https://data.gdeltproject.org/gdeltv2/'
EVENT_FIELDS = (
    'GLOBALEVENTID SQLDATE MonthYear Year FractionDate '
    'Actor1Code Actor1Name Actor1CountryCode Actor1KnownGroupCode Actor1EthnicCode '
    'Actor1Religion1Code Actor1Religion2Code Actor1Type1Code Actor1Type2Code Actor1Type3Code '
    'Actor2Code Actor2Name Actor2CountryCode Actor2KnownGroupCode Actor2EthnicCode '
    'Actor2Religion1Code Actor2Religion2Code Actor2Type1Code Actor2Type2Code Actor2Type3Code '
    'IsRootEvent EventCode EventBaseCode EventRootCode QuadClass GoldsteinScale '
    'NumMentions NumSources NumArticles AvgTone '
    'Actor1Geo_Type Actor1Geo_FullName Actor1Geo_CountryCode Actor1Geo_ADM1Code '
    'Actor1Geo_ADM2Code Actor1Geo_Lat Actor1Geo_Long Actor1Geo_FeatureID '
    'Actor2Geo_Type Actor2Geo_FullName Actor2Geo_CountryCode Actor2Geo_ADM1Code '
    'Actor2Geo_ADM2Code Actor2Geo_Lat Actor2Geo_Long Actor2Geo_FeatureID '
    'ActionGeo_Type ActionGeo_FullName ActionGeo_CountryCode ActionGeo_ADM1Code '
    'ActionGeo_ADM2Code ActionGeo_Lat ActionGeo_Long ActionGeo_FeatureID DATEADDED SOURCEURL'
).split()
GKG_FIELDS = (
    'GKGRECORDID DATE SourceCollectionIdentifier SourceCommonName DocumentIdentifier '
    'Counts V2Counts Themes V2Themes Locations V2Locations Persons V2Persons '
    'Organizations V2Organizations V2Tone Dates GCAM SharingImage RelatedImages '
    'SocialImageEmbeds SocialVideoEmbeds Quotations AllNames Amounts TranslationInfo Extras'
).split()


def stamp(d):
    return d.strftime('%Y%m%d%H%M%S')


def parse_date(s):
    for fmt in ('%Y-%m-%d', '%Y%m%d%H%M%S', '%Y%m%dT%H%M%SZ'):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise ValueError(f'Invalid UTC date: {s}')


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_csv(path, rows, fields):
    # Keep the raw JSON/ZIP for lossless data; CSV uses BOM for Excel.
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


class Client:
    def __init__(self, out, max_requests=64, interval=6):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / 'raw').mkdir()
        self.log = []
        self.maximum = max_requests
        self.interval = max(6, interval)
        self.last = 0

    def get(self, url, suffix):
        for attempt in range(3):
            if len(self.log) >= self.maximum:
                raise RuntimeError('Request budget exhausted; raw responses and partial data are retained.')
            time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
            n = len(self.log) + 1
            dest = self.out / 'raw' / f'{n:04d}{suffix}'
            headers = self.out / 'raw' / f'{n:04d}.headers.txt'
            result = subprocess.run(
                ['curl', '--silent', '--show-error', '--location', '--max-time', '70',
                 '--dump-header', str(headers), '--output', str(dest),
                 '--write-out', '%{http_code}', url], capture_output=True, text=True)
            self.last = time.monotonic()
            body = dest.read_bytes() if dest.exists() else b''
            code = result.stdout.strip()
            message = body[:1500].decode('utf-8', errors='replace')
            limited = code == '429' or 'Please limit requests' in message
            entry = {'url': url, 'fetched_at_utc': datetime.now(UTC).isoformat(),
                     'http_status': code, 'curl_exit': result.returncode,
                     'raw_file': str(dest.relative_to(self.out)), 'bytes': len(body),
                     'sha256': hashlib.sha256(body).hexdigest(), 'rate_limited': limited}
            if result.stderr:
                entry['error'] = result.stderr[:1000]
            self.log.append(entry)
            save_json(self.out / 'requests.json', self.log)
            if result.returncode == 0 and code == '200' and not limited:
                return body
            retryable = limited or code.startswith('5') or result.returncode != 0
            if not retryable or attempt == 2 or len(self.log) >= self.maximum:
                raise RuntimeError(f'HTTP {code}, curl={result.returncode}: {message[:350]}')
            delay = 15 * (2 ** attempt)
            for line in headers.read_text(errors='replace').splitlines() if headers.exists() else []:
                if line.lower().startswith('retry-after:'):
                    try:
                        delay = max(delay, int(line.split(':', 1)[1].strip()))
                    except ValueError:
                        pass
            print(f'Retrying in {delay}s; response saved to {dest}', file=sys.stderr)
            time.sleep(delay)

    def get_json(self, params):
        body = self.get(DOC + '?' + urlencode(params), '.json')
        try:
            return json.loads(body.decode('utf-8-sig'))
        except (ValueError, UnicodeError) as e:
            raise RuntimeError('API returned non-JSON; inspect raw response (not a zero-result search).') from e


def doc(args, client, manifest):
    start, end = parse_date(args.start), parse_date(args.end)
    if start >= end:
        raise ValueError('Require start < end; end is exclusive, all times UTC.')
    if args.sample and end - start > timedelta(days=31):
        raise ValueError('Sample mode accepts at most 31 days; choose a narrower window.')
    seen, windows, pending = {}, [], []
    cursor = start
    while cursor < end:
        boundary = min(cursor + timedelta(days=31), end)
        pending.append((cursor, boundary))
        cursor = boundary
    manifest.update({'query': args.query, 'start_utc': start.isoformat(), 'end_exclusive_utc': end.isoformat(),
                     'sample': args.sample, 'windows': windows, 'unresolved_windows': []})

    def persist():
        records = sorted(seen.values(), key=lambda a: (a.get('seendate', ''), a.get('url', '')))
        save_json(client.out / 'articles.json', {'articles': records})
        write_csv(client.out / 'articles.csv', records,
                  ['seendate', 'title', 'url', 'domain', 'language', 'sourcecountry', 'url_mobile', 'socialimage'])
        manifest['exported_rows'] = len(records)

    try:
        while pending:
            a, b = pending.pop(0)
            params = {'query': args.query, 'mode': 'artlist', 'format': 'json',
                      'maxrecords': args.max_records, 'sort': 'hybridrel',
                      # Query with overlap at the end; local [start,end) filter below is authoritative.
                      'startdatetime': stamp(a), 'enddatetime': stamp(b)}
            try:
                data = client.get_json(params)
            except BaseException:
                pending.insert(0, (a, b))
                raise
            if not isinstance(data, dict) or not isinstance(data.get('articles'), list):
                raise RuntimeError('Missing articles array: inspect response rather than treating it as empty.')
            articles = data['articles']
            win = {'start': stamp(a), 'end': stamp(b), 'returned_rows': len(articles),
                   'at_cap': len(articles) >= args.max_records, 'outside_requested_window': 0}
            windows.append(win)
            for article in articles:
                if not isinstance(article, dict) or not article.get('url') or not article.get('seendate'):
                    raise RuntimeError('Unexpected article schema; retained earlier data.')
                if start <= parse_date(article['seendate']) < end:
                    seen.setdefault(article['url'], article)
                else:
                    win['outside_requested_window'] += 1
            if win['at_cap'] and not args.sample:
                if b - a <= timedelta(minutes=30):
                    manifest['unresolved_windows'].append(win)
                else:
                    # Each child is at least 15 minutes. Overlap is harmless after exact-URL dedup.
                    midpoint = a + timedelta(seconds=int((b - a).total_seconds() // 2))
                    pending[0:0] = [(a, midpoint), (midpoint, b)]
            persist()
    finally:
        manifest['pending_windows'] = [{'start': stamp(a), 'end': stamp(b)} for a, b in pending]
        persist()
    manifest['completeness'] = ('sample_only' if args.sample else
        'incomplete_capped_windows' if manifest['unresolved_windows'] else 'no_observed_cap')
    manifest['interpretation'] = ('No completeness guarantee for all news; scope is GDELT indexed matches. '
        'Exact URL deduplication does not remove syndicated stories. seendate is GDELT observation time; '
        'historical results may be date-bucketed. Inspect raw windows and outside_requested_window.')


def timeline(args, client, manifest):
    start, end = parse_date(args.start), parse_date(args.end)
    if start >= end:
        raise ValueError('Require start < end.')
    data = client.get_json({'query': args.query, 'mode': args.mode, 'format': 'json',
                           'startdatetime': stamp(start), 'enddatetime': stamp(end - timedelta(seconds=1)),
                           'timelinesmooth': 0})
    if not isinstance(data, dict) or not isinstance(data.get('timeline'), list):
        raise RuntimeError('Missing timeline array; inspect raw response.')
    rows = []
    for series in data['timeline']:
        if not isinstance(series, dict) or not isinstance(series.get('data'), list):
            raise RuntimeError('Unexpected timeline series schema.')
        for point in series['data']:
            rows.append({'series': series.get('series', ''), **point})
    fields = list(dict.fromkeys(['series', 'date', 'value'] + [k for r in rows for k in r]))
    save_json(client.out / 'timeline.json', data)
    write_csv(client.out / 'timeline.csv', rows, fields)
    manifest.update({'query': args.query, 'mode': args.mode, 'start_utc': start.isoformat(),
                     'end_exclusive_utc': end.isoformat(), 'exported_rows': len(rows),
                     'completeness': 'aggregate_returned_by_api', 'smoothing': 0,
                     'interpretation': 'Time bucket labels retained exactly as returned; do not assume every row is daily. '
                     'timelinevol is percent, timelinevolraw is article count, timelinetone is mean article tone.'})


def archive(args, client, manifest):
    timestamp = parse_date(args.timestamp)
    if timestamp.minute % 15 or timestamp.second:
        raise ValueError('Archive timestamp must align to a UTC 15-minute boundary.')
    kind = args.command
    suffix = '.export.CSV.zip' if kind == 'events' else '.gkg.csv.zip'
    url = DATA + stamp(timestamp) + suffix
    if args.zip:
        body = Path(args.zip).read_bytes()
        dest = client.out / 'raw' / ('input' + suffix)
        dest.write_bytes(body)
        manifest['local_input'] = {'path': str(Path(args.zip).resolve()),
                                   'sha256': hashlib.sha256(body).hexdigest()}
    else:
        body = client.get(url, suffix)
    fields = EVENT_FIELDS if kind == 'events' else GKG_FIELDS
    rows, total, selected = [], 0, 0
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        members = [p for p in z.infolist() if not p.is_dir()]
        if len(members) != 1:
            raise RuntimeError('Expected one data file per GDELT ZIP.')
        with z.open(members[0]) as f:
            # These files are TSV despite their .CSV extension. No CSV quoting is applied.
            for values in csv.reader(io.TextIOWrapper(f, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
                if len(values) != len(fields):
                    raise RuntimeError(f'Expected {len(fields)} columns, got {len(values)} at row {total + 1}.')
                total += 1
                row = dict(zip(fields, values))
                if kind == 'events':
                    pair = (row['Actor1CountryCode'], row['Actor2CountryCode'])
                    if pair not in ((args.actor1, args.actor2), (args.actor2, args.actor1)):
                        continue
                else:
                    if args.theme and args.theme not in row['Themes'].split(';'):
                        continue
                    countries = {p.split('#')[2] for p in row['V2Locations'].split(';') if len(p.split('#')) >= 3}
                    if not set(args.countries or []).issubset(countries):
                        continue
                selected += 1
                rows.append(row)
    write_csv(client.out / (kind + '.csv'), rows, fields)
    save_json(client.out / (kind + '.json'), rows)
    manifest.update({'source_url': url, 'timestamp_utc': timestamp.isoformat(),
                     'input_rows': total, 'exported_rows': selected, 'columns': len(fields),
                     'completeness': 'one_15_minute_update_only',
                     'filter': {'actor_pair_bidirectional': [args.actor1, args.actor2]} if kind == 'events' else
                               {'exact_theme': args.theme, 'location_fips_all_required': args.countries},
                     'interpretation': 'Candidate records, not validated trade-war events. '
                     'Archive time is ingestion time, not necessarily event date. '
                     'Location co-occurrence in GKG does not establish a bilateral interaction.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for kind in ('doc', 'timeline', 'events', 'gkg'):
        p = sub.add_parser(kind)
        p.add_argument('--out', required=True, help='New output directory; existing directories are never overwritten')
        p.add_argument('--max-requests', type=int, default=64)
        p.add_argument('--interval', type=float, default=6, help='Seconds, minimum 6; do not run clients concurrently')
        if kind in ('doc', 'timeline'):
            p.add_argument('--query', required=True)
            p.add_argument('--start', required=True, help='YYYY-MM-DD or YYYYMMDDHHMMSS UTC')
            p.add_argument('--end', required=True, help='Exclusive end, same formats, UTC')
        if kind == 'doc':
            p.add_argument('--max-records', type=int, choices=range(1, 251), default=250, metavar='1..250')
            p.add_argument('--sample', action='store_true', help='Do not split capped responses; explicitly label as sample')
        if kind == 'timeline':
            p.add_argument('--mode', choices=['timelinevolraw', 'timelinevol', 'timelinetone'], default='timelinevolraw')
        if kind in ('events', 'gkg'):
            p.add_argument('--timestamp', required=True, help='UTC YYYYMMDDHHMMSS, aligned to 15 minutes')
            p.add_argument('--zip', help='Process a previously downloaded ZIP offline')
        if kind == 'events':
            p.add_argument('--actor1', default='CHN')
            p.add_argument('--actor2', default='USA')
        if kind == 'gkg':
            p.add_argument('--theme', help='Exact Themes token, e.g. ECON_TRADE_DISPUTE')
            p.add_argument('--countries', nargs='*', help='Require all location FIPS codes, e.g. CH US')
    args = parser.parse_args()
    if args.max_requests < 1:
        parser.error('--max-requests must be positive')
    client = Client(args.out, args.max_requests, args.interval)
    manifest = {'command': args.command, 'created_at_utc': datetime.now(UTC).isoformat(),
                'arguments': vars(args), 'status': 'running', 'timezone': 'UTC',
                'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save_json(client.out / 'manifest.json', manifest)
    try:
        if args.command == 'doc':
            doc(args, client, manifest)
        elif args.command == 'timeline':
            timeline(args, client, manifest)
        else:
            archive(args, client, manifest)
        manifest['status'] = 'success'
    except (Exception, KeyboardInterrupt) as e:
        manifest.update({'status': 'failed', 'error': str(e), 'completeness': 'incomplete_failed_run'})
        print(f'ERROR: {e}', file=sys.stderr)
    finally:
        manifest['request_count'] = len(client.log)
        manifest['finished_at_utc'] = datetime.now(UTC).isoformat()
        save_json(client.out / 'manifest.json', manifest)
    print(json.dumps({k: manifest[k] for k in ('status', 'exported_rows', 'completeness') if k in manifest}, ensure_ascii=False))
    return 0 if manifest['status'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
