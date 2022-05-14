from soupspoon import Link


def get_wikipedia_link(url, base_url='http://en.wikipedia.org'):
	base_url = base_url.rstrip('/')

	if url.startswith('/wiki/'):
		return base_url + url
	elif url.startswith('wiki/'):
		return base_url + '/' + url
	elif url.startswith('http://en.wikipedia.org/wiki'):
		return url
	else:
		return None


def find_wikipedia_links(obj, base_url='http://en.wikipedia.org'):
	"""
	:type obj: list or dict or tuple or str
	"""
	if obj is None:
		return []

	elif isinstance(obj, Link):
		return find_wikipedia_links(obj=obj.url, base_url=base_url)

	elif isinstance(obj, str):
		try:
			link = get_wikipedia_link(url=obj, base_url=base_url)
			return [link]
		except:
			pass
	elif isinstance(obj, (list, tuple, dict)):
		if isinstance(obj, dict):
			results = [
				find_wikipedia_links(k, base_url=base_url) + find_wikipedia_links(v, base_url=base_url)
				for k, v in obj.items()
			]
		else:
			results = [find_wikipedia_links(x, base_url=base_url) for x in obj]

		uniques = set()
		flat_result = []
		for l in results:
			for x in l:
				if x not in uniques and x is not None:
					uniques.add(x)
					flat_result.append(x)
		return flat_result

	else:
		return []
