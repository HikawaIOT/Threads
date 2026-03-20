#!/usr/bin/env python3
import json
import pathlib
import datetime
import os
import requests

base = pathlib.Path(__file__).resolve().parents[1]
q_path = base / 'data/posts_queue.json'
log_path = base / 'data/posted_log.json'
state_path = base / 'data/state.json'
env_path = base / '.env'


def load_env(path: pathlib.Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())


def publish_to_threads(text: str):
    load_env(env_path)
    uid = os.environ.get('THREADS_USER_ID')
    token = os.environ.get('THREADS_ACCESS_TOKEN')
    if not uid or not token:
        raise RuntimeError('THREADS_USER_ID or THREADS_ACCESS_TOKEN is missing in .env')

    base_url = 'https://graph.threads.net/v1.0'

    create = requests.post(
        f'{base_url}/{uid}/threads',
        data={
            'media_type': 'TEXT',
            'text': text,
            'access_token': token,
        },
        timeout=30,
    )
    create.raise_for_status()
    creation_id = create.json().get('id')
    if not creation_id:
        raise RuntimeError('No creation id returned from Threads API')

    publish = requests.post(
        f'{base_url}/{uid}/threads_publish',
        data={
            'creation_id': creation_id,
            'access_token': token,
        },
        timeout=30,
    )
    publish.raise_for_status()
    return publish.json().get('id')


def main():
    queue = json.loads(q_path.read_text())
    posted = json.loads(log_path.read_text())
    state = json.loads(state_path.read_text())

    if state.get('paused'):
        print('poster: paused')
        return

    item = next((x for x in queue if x.get('status') == 'ready'), None)
    if not item:
        print('poster: no ready posts')
        return

    text = item.get('text', '').strip()
    if not text:
        item['status'] = 'error'
        item['error'] = 'empty text'
        queue_path = q_path
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
        state['errors'] = int(state.get('errors', 0)) + 1
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print('poster: empty text error')
        return

    try:
        post_id = publish_to_threads(text)
        item['status'] = 'posted'
        item['posted_at'] = datetime.datetime.now().isoformat(timespec='seconds')
        item['threads_post_id'] = post_id
        posted.append(item)
        state['last_posted_at'] = item['posted_at']
        state['errors'] = 0

        q_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
        log_path.write_text(json.dumps(posted, ensure_ascii=False, indent=2))
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print(f"poster: posted={item['id']} threads_post_id={post_id}")

    except Exception as e:
        item['status'] = 'error'
        item['error'] = str(e)
        state['errors'] = int(state.get('errors', 0)) + 1
        q_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print(f'poster: error={e}')


if __name__ == '__main__':
    main()
