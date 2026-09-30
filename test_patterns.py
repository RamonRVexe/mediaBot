import unittest
from types import SimpleNamespace

from downloader.series import (
	_parsear_mensaje_episodio,
	_registrar_temporada_tema,
	_temporada_del_tema,
	parse_episode,
)


class EpisodePatternTests(unittest.TestCase):
	def test_episode_only_name_requires_topic_season(self):
		self.assertIsNone(parse_episode("Episodio 2."))

	def test_episode_only_name_uses_topic_season(self):
		self.assertEqual(
			parse_episode("Episodio 17.", temporada=2),
			(2, 17, "Episodio")
		)

	def test_topic_title_provides_season(self):
		temporadas_tema = {}
		topic = SimpleNamespace(
			id=42,
			action=SimpleNamespace(title="Temporada 3")
		)
		message = SimpleNamespace(
			reply_to=SimpleNamespace(
				reply_to_top_id=42,
				reply_to_msg_id=42
			)
		)

		_registrar_temporada_tema(topic, temporadas_tema)

		self.assertEqual(_temporada_del_tema(message, temporadas_tema), 3)

	def test_episode_caption_uses_topic_season(self):
		temporadas_tema = {42: 4}
		message = SimpleNamespace(
			file=SimpleNamespace(name=""),
			message="Episodio 9.",
			reply_to=SimpleNamespace(reply_to_top_id=42)
		)

		parsed, nombre = _parsear_mensaje_episodio(
			message,
			temporadas_tema
		)

		self.assertEqual(parsed, (4, 9, "Episodio"))
		self.assertEqual(nombre, "Episodio 9.")


if __name__ == "__main__":
	unittest.main()
