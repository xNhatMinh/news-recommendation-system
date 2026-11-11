import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from contextlib import redirect_stdout
import io

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
ROOT=Path(__file__).resolve().parents[2]

class PipelineTests(unittest.TestCase):
    def run_pipeline(self,enabled=None,selected=None,fail=None):
        codes=['vnexpress','dantri','tuoitre','vietnamnet']
        sources=[{'code':code,'name':code,'enabled':code in (enabled if enabled is not None else codes)} for code in codes]
        modules={}
        crawlers={}
        for code in codes:
            module=types.ModuleType('src.crawler.'+code+'_crawler')
            module.main=Mock(side_effect=RuntimeError() if code==fail else None,return_value=[{'url':code}])
            modules[module.__name__]=module;crawlers[code]=module.main
        settings=types.ModuleType('src.db.admin_store')
        settings.init_admin_tables=Mock();settings.get_sources=Mock(return_value=sources)
        settings.source_started=Mock();settings.source_finished=Mock();modules[settings.__name__]=settings
        embed=types.ModuleType('src.embedding.generate_embeddings');embed.main=Mock();modules[embed.__name__]=embed
        notify=types.ModuleType('src.notifications.service');notify.notify_new_articles=Mock();modules[notify.__name__]=notify
        with patch.dict(sys.modules,modules),redirect_stdout(io.StringIO()):
            spec=importlib.util.spec_from_file_location('pipeline_check',ROOT/'src/update_news.py')
            pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
            result=pipeline.main(sources=selected)
        return result,crawlers,settings,embed,notify

    def test_all_enabled_sources(self):
        result,crawlers,settings,embed,notify=self.run_pipeline()
        self.assertEqual(result['new_articles'],4)
        self.assertEqual(settings.source_started.call_count,4)
        embed.main.assert_called_once();notify.notify_new_articles.assert_called_once()

    def test_disabled_and_unselected_sources_not_called(self):
        result,crawlers,settings,embed,notify=self.run_pipeline(enabled=['vnexpress','tuoitre'],selected=['tuoitre'])
        crawlers['tuoitre'].assert_called_once_with(days=2,limit_per_category=5)
        for code in ['vnexpress','dantri','vietnamnet']:crawlers[code].assert_not_called()
        self.assertEqual(result['new_articles'],1)

    def test_all_disabled_skips_processing(self):
        result,crawlers,settings,embed,notify=self.run_pipeline(enabled=[])
        self.assertEqual(result['new_articles'],0);embed.main.assert_not_called();notify.notify_new_articles.assert_not_called()

    def test_source_failure_does_not_stop_other_sources(self):
        result,crawlers,settings,embed,notify=self.run_pipeline(fail='tuoitre')
        self.assertEqual(result['status'],'partial');self.assertEqual(result['new_articles'],3)
        settings.source_finished.assert_any_call('tuoitre',error='RuntimeError')
        embed.main.assert_called_once();notify.notify_new_articles.assert_called_once()

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):self.run_pipeline(selected=['unknown'])

if __name__=='__main__':unittest.main(verbosity=2)
