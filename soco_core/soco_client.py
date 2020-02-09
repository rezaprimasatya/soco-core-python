import requests
from uuid import uuid4
import json
import time
from typing import Sequence, Generator
from tqdm import tqdm


class SOCOClient(object):
    def __init__(self, api_key):
        self.api_key = api_key
        self._server_url = 'https://api.soco.ai'
        self._server_url = 'http://localhost:6000'

        # MONITOR
        self.status_url = self._server_url + '/v1/index/status'

        # QUERY
        self.query_url = self._server_url + '/v2/search/query'
        self.aggregate_url = self._server_url + '/v1/search/aggregate'

        # INDEX
        self.publish_url = self._server_url + '/v1/index/publish'
        self.abort_url = self._server_url + '/v1/index/abort'
        self.add_url = self._server_url + '/v1/index/add'
        self.read_url = self._server_url + '/v1/index/read'
        self.delete_url = self._server_url + '/v1/index/delete'

    def _get_header(self):
        return {'Content-Type': 'application/json', "Authorization": self.api_key}

    def _check_fields(self, fields, object):
        for f in fields:
            if f not in object['answer']:
                raise Exception("{} is required inside answer".format(f))

    def _check_frame_format(self, data):
        for frame in data:
            if 'answer' not in frame:
                raise Exception("answer is required for frame")
            self._check_fields(['value', 'context', 'answer_start'], frame)

            # check questions
            if 'questions' in frame:
                if type(frame['questions']) is not list:
                    raise Exception("Expect list for questions")
                for q in frame['questions']:
                    self._check_fields(['value'], q)

    def _check_doc_format(self, data):
        for doc in data:
            if 'data' not in doc:
                raise Exception("data is required for a doc")

            if type(doc['data']) is not list:
                raise Exception("data should be a list.")

            # check questions
            if 'meta' in doc:
                if type(doc['meta']) is not dict:
                    raise Exception("meta should be a dict")

    def _chunks(self, l: Sequence, n: int = 100) -> Generator[Sequence, None, None]:
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            is_last = i + n >= len(l)
            is_first = i == 0
            yield l[i:i + n]

    def wait_for_ready(self, check_frequency=2, timeout=-1, verbose=False):
        start_time = time.time()
        time.sleep(0.5)
        while True:
            state = self.status()
            if state['status'] == 'ready':
                break

            elapsed_time = int(time.time() - start_time)
            if verbose:
                print("Have waited {} seconds with index size {}".format(int(time.time() - start_time), state['size']))

            if 0 < timeout < elapsed_time:
                print("Time out!")
                return

            time.sleep(check_frequency)

        print("Index is ready!")

    def query(self, query, n_best, uid=None, alpha_bm25=0, use_mrc=False, max_l2r=-1, filters=None):
        data = {
            "query": query,
            "n_best": n_best,
            "uid": uid if uid is not None else str(uuid4())
        }
        args = {'alpha_bm25': alpha_bm25, 'use_mrc': use_mrc, 'max_l2r': max_l2r, 'filters': filters}
        data.update(**args)
        result = requests.post(self.query_url, json=data, headers=self._get_header(), timeout=60)
        if result.status_code >= 300:
            print("Error in connecting to the SOCO servers")
            return None

        return json.loads(result.text)

    def aggregate(self, query, size, query_args, agg_args, uid=None):
        data = {
            "query": query,
            "n_best": size,
            "uid": uid if uid is not None else str(uuid4()),
            "query_args": query_args,
            "agg_args": agg_args
        }
        result = requests.post(self.aggregate_url, json=data, headers=self._get_header(),
                               timeout=60)
        if result.status_code >= 300:
            print("Error in connecting to the SOCO servers")
            return None

        return json.loads(result.text)

    def status(self):
        result = requests.get(self.status_url, headers=self._get_header())
        if result.status_code >= 300:
            print("Error in connecting to the SOCO servers")
            return None
        return json.loads(result.text)

    @classmethod
    def pprint(cls, results):
        for r in results['results']:
            print("({}) - {}".format(r['score'], r['a']['value']))

    def add_data(self, data):
        self._check_doc_format(data)
        job_results = []
        batch_size = 100
        for batch in tqdm(self._chunks(data, n=batch_size), desc='Adding {} docs to task'.format(len(data))):
            data = {"data": batch}
            result = requests.post(self.add_url, json=data, headers=self._get_header())
            if result.status_code >= 300:
                print("Error in appending to index at SOCO servers")
                return None
            job_results.append(json.loads(result.text))

        return job_results

    def read_data(self, batch_size=100):
        data = []
        skip = 0
        limit = batch_size
        while True:
            results = requests.post(self.read_url, json={'skip': skip, 'limit': limit}, headers=self._get_header())
            batch_docs = results.json()
            data.extend(batch_docs)
            if len(batch_docs) < limit:
                break
            skip = len(data)

        return data

    def delete_data(self, doc_ids=None):
        if doc_ids is None:
            result = requests.post(self.delete_url, headers=self._get_header())
        else:
            result = requests.post(self.delete_url,
                                           json={'doc_ids': doc_ids},
                                           headers=self._get_header())
        return result

    def publish(self, encoder_id, db_encoder_id, publish_args):
        body = {'encoder_id': encoder_id,
                'db_encoder_id': db_encoder_id,
                'publish_args': publish_args}
        result = requests.post(self.publish_url, json=body, headers=self._get_header())
        return result

    def abort(self):
        result = requests.post(self.abort_url, headers=self._get_header())
        return result


