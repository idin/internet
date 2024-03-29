from copy import deepcopy
import requests
from requests.adapters import SSLError
import time
import warnings
import re

from chronometry import MeasurementSet, get_elapsed, get_now
from abstract import Graph

from .exceptions import HTTPTimeoutError, WikipediaException
from .WikipediaPage import WikipediaPage
from .WikipediaMemory import WikipediaMemory
from .get_special_data import get_special_data
from .Page_helpers import get_search_parameters


class Wikipedia:
	def __init__(
			self, language='en',
			user_agent='wikipedia (https://github.com/goldsmith/Wikipedia/)',
			rate_limit_wait_seconds=0.01,
			cache=None,
			num_request_tries=4
	):
		"""
		:param str language: such as 'en'
		:param str user_agent:
		:param float rate_limit_wait_seconds: wait between requests
		:param disk.Cache.Cache cache:
		"""
		self._language = language
		self._user_agent = user_agent
		self._rate_limit_wait = rate_limit_wait_seconds
		self._rate_limit_last_call = None
		self._num_request_tries = num_request_tries

		self._memory = None
		self._has_memory = False
		# if self.has_memory():
		# 	self._memory = WikipediaMemory(path=self._pickle_path)

		self._cache = cache
		if self._cache:
			self.request = self._cache.make_cached(
				id='wikipedia_request_function',
				function=self._request,
				condition_function=self._request_result_valid,
				sub_directory='request'
			)

		else:
			self.request = self._request

		self._function_durations = MeasurementSet()

	def __hashkey__(self):
		return (self.__class__.__name__, self._language, self._user_agent, self._rate_limit_wait, self._cache)

	def __getstate__(self):
		return {
			'language': self._language,
			'user_agent': self._user_agent,
			'rate_limit_wait': self._rate_limit_wait,
			'rate_limit_last_call': self._rate_limit_last_call,
			'cache': self._cache,
			'function_durations': self._function_durations
		}

	def __setstate__(self, state):
		self._language = state['language']
		self._user_agent = state['user_agent']
		self._rate_limit_wait = state['rate_limit_wait']
		self._rate_limit_last_call = state['rate_limit_last_call']
		self._cache = state['cache']
		self._function_durations = state['function_durations']
		if self._cache:
			self.request = self._cache.make_cached(
				id='wikipedia_request_function',
				function=self._request,
				condition_function=self._request_result_valid,
				sub_directory='request'
			)

		else:
			self.request = self._request

	def __eq__(self, other):
		"""
		:type other: Wikipedia
		:rtype: bool
		"""
		if isinstance(other, self.__class__):
			return self._language == other._language
		else:
			return False

	@property
	def memory(self):
		"""
		:rtype: WikipediaMemory
		"""
		return self._memory

	@property
	def cache(self):
		"""
		:rtype: disk.Cache or NoneType
		"""
		return self._cache

	@property
	def function_durations(self):
		"""
		:rtype: MeasurementSet
		"""
		return self._function_durations

	@property
	def language(self):
		return self._language.lower()

	@property
	def api_url(self):
		return 'http://' + self.language + '.wikipedia.org/w/api.php'

	@staticmethod
	def _request_result_valid(result, **kwargs):
		return result is not None

	def _request(self, parameters=None, url=None, format='json'):
		"""
		:type parameters: dict
		:rtype: dict
		"""
		memory_key = (parameters, url, format)

		if self.has_memory():
			results = self.memory.get_request_result(key=memory_key)
			if results:
				print('getting request from memory!')
				return results

		_format = format
		for i in range(1, self._num_request_tries + 1):

			headers = {'User-Agent': self._user_agent}
			try:
				if _format == 'json':
					if parameters is None:
						raise ValueError('parameters cannot be empty for json request!')
					parameters['format'] = 'json'
					if 'action' not in parameters:
						parameters['action'] = 'query'
				else:
					if url is None:
						raise ValueError('url cannot be empty for non-json request!')

				if self._rate_limit_wait and self._rate_limit_last_call:
					wait_time = self._rate_limit_wait - get_elapsed(start=self._rate_limit_last_call, unit='s')
					if wait_time > 0:
						time.sleep(wait_time)

				if _format == 'json':
					r = requests.get(self.api_url, params=parameters, headers=headers)
					result = r.json()

				else:
					result = requests.get(url, headers=headers)

				break

			except SSLError as e:
				print(f'try {i}, error with get request with url="{url}", headers="{headers}", format="{_format}"')
				warnings.warn(str(e))
				time.sleep(0.001 * 10 ** i)


		else:
			raise e

			# result = html.document_fromstring(r.text)
			# result = r.text

		if self._rate_limit_wait:
			self._rate_limit_last_call = get_now()

		if self.has_memory():
			self.memory.set_request_result(key=memory_key, results=result)
		return result

	def has_memory(self):
		return self._has_memory

	def save_memory(self):
		if self.has_memory():
			self.memory.save_to_file()

	def get_page(self, url=None, id=None, title=None, namespace=0, redirect=True, n_jobs=1):
		"""
		:type id: int or str or NoneType
		:type url: str or NoneType
		:type title: str or NoneType
		:rtype: WikipediaPage
		"""
		key = (url, id, title, namespace, redirect)

		if self.has_memory():
			page = self.memory.get_page(key=key)
			if page :
				return page

		page = WikipediaPage(
			id=id, url=url, title=title, namespace=namespace, wikipedia=self, redirect=redirect,
			n_jobs=n_jobs
		)

		if self.has_memory():
			self.memory.set_page(key=key, page=page)

		return page

	def get_page_graph(
			self, graph=None, id=None, url=None, title=None, namespace=0, redirect=True,
			max_depth=1, strict=True, ordering=True, echo=1
	):
		try:
			if graph:
				graph = deepcopy(graph)
			else:
				graph = Graph(obj=None, strict=strict, ordering=ordering)

			def _crawl(_graph, _page, _parent_page, _max_depth, _depth, _echo, _crawl_completed):
				if _page['url'] not in _graph:
					_graph.add_node(name=_page['url'], label=_page['title'], value=_page)

				if _parent_page is not None:
					_graph.connect(start=_parent_page['url'], end=_page['url'], if_edge_exists='ignore')

				# to avoid crawling the children of a page for a second time we add the url of the parent page in
				# crawl_completed at the end
				if _page['url'] not in _crawl_completed and _depth < _max_depth:
					for child in _page.get_children(echo=_echo):
						_crawl(
							_graph=_graph, _page=child,
							_parent_page=_page, _max_depth=_max_depth, _depth=_depth + 1, _echo=_echo,
							_crawl_completed=_crawl_completed
						)
					_crawl_completed.append(_page['url'])

			page = self.get_page(id=id, url=url, title=title, namespace=namespace, redirect=redirect)
			_crawl(
				_graph=graph, _page=page, _parent_page=None,
				_max_depth=max_depth, _echo=echo, _depth=0, _crawl_completed=[]
			)
			return graph
		except KeyboardInterrupt:
			warnings.warn('get_page_graph was interrupted by keyboard!')
			return graph

	def get_url_from_page_id(self, page_id):
		search_query_parameters = get_search_parameters(id=page_id, title=None)
		search_request = self.request(parameters=search_query_parameters, format='json')
		return search_request['query']['pages'][str(page_id)]['fullurl']

	def search(self, query, num_results=10, redirect=True):
		"""
		Do a Wikipedia search for `query`.
		:type query: str
		:param int num_results: the maxmimum number of results returned
		:type redirect: bool
		"""

		search_params = {
			'list': 'search',
			'srprop': '',
			'srlimit': num_results,
			'limit': num_results,
			'srsearch': query
		}

		raw_results = self.request(search_params)

		if 'error' in raw_results:
			if raw_results['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
				raise HTTPTimeoutError(query)
			else:
				raise WikipediaException(raw_results['error']['info'])

		results = raw_results['query']['search']

		try:
			page_ids = [x['pageid'] for x in results]
			urls = [self.get_url_from_page_id(page_id=page_id) for page_id in page_ids]
			pages = [self.get_page(url=url) for url in urls]
			return pages
		except:
			pass

		try:
			pages = [
				WikipediaPage(wikipedia=self, id=d['pageid'], title=d['title'], namespace=d['ns'], redirect=redirect) for d in results
			]
		except Exception as e:
			print('\n'*5, 'error in:\n', results, '\n'*5)
			raise e

		already_captured_urls = [page.url for page in pages]
		disambiguation_pages = [page for page in pages if page['disambiguation']]
		disambiguation_results = []
		total_num_results = len(pages)
		for disambiguation_page in disambiguation_pages:
			for link in disambiguation_page['disambiguation_results']:
				if link.url not in already_captured_urls and total_num_results<num_results:
					wikipedia_url_regex_str = '^(http|https)://.+\.wikipedia.org'
					wikipedia_url_regex = re.compile(wikipedia_url_regex_str)
					if re.match(wikipedia_url_regex, link['url']):
						page = WikipediaPage(
							wikipedia=self, url=link.url, title=link.text,
							disambiguation_url=disambiguation_page['url']
						)
						disambiguation_results.append(page)
						total_num_results += 1
		return pages + disambiguation_results

	def get_performance(self):
		return self.function_durations.summary_data

	def get_data(self, name, echo=1):
		return get_special_data(wikipedia=self, name=name, echo=echo)
