import tldextract
from soupspoon import Link


def get_domain_and_tld(url):
	"""
	return the domain and tld: forums.news.cnn.com/index.html --> cnn.com, http://bbc.co.uk --> bbc.co.uk
	:type url: str
	:rtype: str
	"""
	if url is None:
		return None

	ext = tldextract.extract(url)
	result = f'{ext.domain}.{ext.suffix}'
	if result.endswith('.'):
		return None
	else:
		return result


def find_domains(obj):
	"""
	:type obj: list or dict or tuple or str
	"""
	if obj is None:
		return []

	elif isinstance(obj, Link):
		return find_domains(obj.url)

	elif isinstance(obj, str):
		try:
			domain = get_domain_and_tld(obj)
			return [domain]
		except:
			pass
	elif isinstance(obj, (list, tuple, dict)):
		if isinstance(obj, dict):
			results = [find_domains(k) + find_domains(v) for k, v in obj.items()]
		else:
			results = [find_domains(x) for x in obj]

		uniques = set()
		flat_result = []
		for l in results:
			for x in l:
				if x is not None:
					lower = x.lower()
					if lower not in uniques:
						uniques.add(lower)
						flat_result.append(x)
		return flat_result
	else:
		return []