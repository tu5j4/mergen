"""QML presentation bridge. Model packages are only imported by child processes."""
import json
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot, QThread, QTimer, QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from dataclasses import replace
from app.config import Settings, LANGS
from app.storage import DATA_ROOT, APP_ROOT, VERSION, prepare_data
from installer.catalog import COMPONENTS
from installer import service


class Job(QThread):
    progress=Signal(str)
    result=Signal(object)
    failed=Signal(str)
    def __init__(self, fn, parent=None): super().__init__(parent);self.fn=fn
    def run(self):
        try: self.result.emit(self.fn(self.progress.emit))
        except Exception as exc: self.failed.emit(str(exc))


class Controller(QObject):
    changed=Signal()
    confirmation=Signal(str,str)
    navigate=Signal(int)
    def __init__(self):
        super().__init__()
        prepare_data()
        self.settings=Settings.load()
        for name in ('translation_backend','ocr_backend','manga_backend'):
            if getattr(self.settings,name)=='local': setattr(self.settings,name,'cpu')
        self.settings.save()
        self.backend=None;self.job=None;self._pending=None;self._stopping=False
        self._state={'version':VERSION,'status':'Okumaya hazır.','running':False,'busy':False,'log':'',
                     'components':[],'hardware':'Donanım bilgileri alınıyor…','updates':'Henüz kontrol edilmedi.',
                     'validation':[],'validationSummary':'model testi henüz çalıştırılmadı.','operationTitle':'bileşen durumu','phase':'indirme ve kurulum ayrıntıları burada görünür.','activeComponent':'','progress':-1,
                     'updateAvailable':False,'recommendation':'Donanım kontrol ediliyor…','dataPath':str(DATA_ROOT),'usage':{'gpu':'—','vram':'—','cpu':'—'}}
        from app.ui.usage_monitor import UsageMonitor
        self.monitor=UsageMonitor(self);self.monitor.readings.connect(self.usage)
        enabled=any((self.settings.show_gpu_usage,self.settings.show_vram_usage,self.settings.show_cpu_usage))
        self.monitor.set_enabled(enabled and self.settings.show_gpu_usage,enabled and self.settings.show_vram_usage,enabled and self.settings.show_cpu_usage)
        from app.ui.control_panel import HotkeyBridge, start_global_hotkeys
        self.bridge=HotkeyBridge()
        self.bridge.toggle_run.connect(lambda:self.action('start'))
        self.bridge.select_region.connect(lambda:self.action('region'))
        self.bridge.toggle_overlay.connect(lambda:self.action('overlay'))
        self.bridge.translate_now.connect(lambda:self.action('once'))
        self.hotkeys=start_global_hotkeys(self.bridge)
        QApplication.instance().aboutToQuit.connect(self.stop_hotkeys)
        QTimer.singleShot(0,self.refresh)
        if self.settings.check_updates: QTimer.singleShot(6000,lambda:self.settings.check_updates and self.action('check-update'))

    def stop_hotkeys(self):
        if self.hotkeys:
            self.hotkeys.stop()

    @Property('QVariantMap',notify=changed)
    def state(self):
        return dict(self._state,theme=self.settings.panel_theme,language=self.settings.source_lang,
            translationBackend=self.settings.translation_backend,ocrBackend=self.settings.ocr_backend,
            mangaBackend=self.settings.manga_backend,model='1300m' if '1.3B' in self.settings.translation_model else '600m',
            opacity=self.settings.overlay_opacity,mangaEnabled=self.settings.use_manga_ocr,
            overlayTheme=self.settings.theme,fontFamily=self.settings.font_family,maxFont=self.settings.max_font_px,
            bold=self.settings.font_bold,preset=self.settings.speed_preset,scrollTracking=self.settings.scroll_tracking,
            contextEnabled=self.settings.session_context,chinesePivot=self.settings.chinese_translation_via_english,
            shareTranslations=self.settings.share_translations,
            checkUpdates=self.settings.check_updates,showGpu=self.settings.show_gpu_usage,
            showVram=self.settings.show_vram_usage,showCpu=self.settings.show_cpu_usage,
            showUsage=any((self.settings.show_gpu_usage,self.settings.show_vram_usage,self.settings.show_cpu_usage)))

    def status(self,text): self._state['status']=str(text).replace('İ','i').lower();self.changed.emit()
    def usage(self,values):
        self._state['usage'].update({k:(str(v)+'%' if v is not None else '—') for k,v in values.items()});self.changed.emit()
    def append(self,line):
        if line.startswith('@mergen:'):
            data=json.loads(line[8:])
            self._state['phase']=data.get('phase',self._state['phase'])
            self._state['progress']=data.get('progress',self._state['progress'])
            if data.get('kind')=='component':
                self._state['activeComponent']=data['key'];self.scan_components()
            elif data.get('kind')=='validation':
                row=data['row']
                rows=[r for r in self._state['validation'] if r['task']!=row['task']]
                rows.append(row);self._state['validation']=rows
            self.changed.emit();return
        self._state['log']=(self._state['log']+'\n'+line)[-24000:];self.changed.emit()

    def scan_components(self):
        self._state['components']=[dict(v,key=k) for k,v in service.inventory().items()]

    def job_error(self,message):
        self._state['phase']='işlem tamamlanamadı · '+message
        self._state['operationTitle']='işlem tamamlanamadı'
        self._state['validationSummary']='işlem tamamlanamadı; günlüğü kontrol edip yeniden deneyebilirsin.'
        self.append(message);self.status(message)

    def validation_done(self,report):
        self._state['validation']=report['rows']
        self._state['validationSummary']='tüm model testleri geçti · çeviri hazır.' if report['ok'] else 'eksik veya başarısız bileşenler var; aşağıdaki sonuçları kontrol et.'
        self._state['phase']=self._state['validationSummary']
        self._state['operationTitle']='doğrulama tamamlandı' if report['ok'] else 'doğrulama tamamlanamadı'
        self._state['progress']=100
        self.status(self._state['validationSummary'])


    def start_job(self,fn,done=None):
        if self.job is not None or self._stopping: self.status('Devam eden işlemin tamamlanmasını bekleyin.');return
        self._state['busy']=True;self.changed.emit()
        self.job=Job(fn,self)
        self.job.progress.connect(self.append)
        self.job.failed.connect(self.job_error)
        self._job_done=done;self._job_result=None;self._job_ok=False
        self.job.result.connect(self.job_result)
        self.job.finished.connect(self.job_finished)
        self.job.start()
    def job_result(self,result):
        self._job_result=result;self._job_ok=True
    def job_finished(self):
        job,self.job=self.job,None;job.deleteLater();self._state['busy']=False;self.changed.emit()
        done=self._job_done
        if self._job_ok and done:
            try:done(self._job_result)
            except Exception as exc:self.status(str(exc))
        QTimer.singleShot(0,self.refresh)

    @Slot()
    def refresh(self):
        if self.job is not None:return
        # Package scanning uses ready markers, so refresh never imports model runtimes.
        self.scan_components()
        if self._state['hardware'].startswith('Donanım'):
            from installer.hardware import detect
            self.start_job(lambda emit:detect(),self.hardware_ready)
        self.changed.emit()
    def hardware_ready(self,data):
        adapters=data.get('adapters',[])
        self._state['hardware']=' · '.join(a['name'] for a in adapters) or 'GPU bilgisi okunamadı. CPU kullanılabilir.'
        from installer.profiles import recommended
        self._profile=recommended(data)
        self._state['recommendation']=self._profile['message']
        self.changed.emit()

    def ensure_backend(self):
        if self.backend is not None:return self.backend
        from app.ui.control_panel import ControlPanel
        owner=self
        class Backend(ControlPanel):
            def _set_status(self,text):
                super()._set_status(text);owner._state['running']=self.running;owner.status(text)
            def _on_worker_error(self,msg):
                owner.status('Hata: '+msg);owner.release_backend()
            def _show_settings(self): owner.navigate.emit(1)
        self.settings.save();self.backend=Backend(enable_hotkeys=False)
        self.backend.usage_monitor.close()
        self.backend.bridge.toggle_run.connect(lambda:self._state.update(running=self.backend.running))
        self.backend.settings_dialog.hide()
        return self.backend

    def release_backend(self,after=None):
        if self._stopping:return
        backend=self.backend
        def finish():
            if backend:
                backend.usage_monitor.close()
                if getattr(backend,'_selector',None):backend._selector.close()
                backend.overlay.close();backend.settings_dialog.close()
                if backend.hotkeys:backend.hotkeys.stop()
                backend.deleteLater()
            self.backend=None;self._stopping=False;self._state['running']=False;self.changed.emit()
            if after:after()
        if backend and backend.thread is not None and backend.thread.isRunning():
            self._stopping=True;self.status('Modeller kapatılıyor…')
            backend.thread.finished.connect(finish)
            backend.worker.stop();backend.thread.quit()
        else: finish()

    @Slot(str,'QVariant')
    def setting(self,key,value):
        choices={'panel_theme':('green','white','navy','black','sepia'),
                 'source_lang':tuple(LANGS),'translation_backend':('cpu','nvidia','amd','intel'),
                 'ocr_backend':('cpu','nvidia','amd','intel'),'manga_backend':('cpu','nvidia','amd','intel'),
                 'translation_model':('nllb-200-distilled-600M-ct2','nllb-200-distilled-1.3B-ct2'),
                 'theme':('white','black','sepia','navy','gray'), 'font_family':('Segoe UI','Comic Sans MS','Arial'),
                 'speed_preset':('fast','balanced','quality')}
        booleans=('use_manga_ocr','check_updates','show_gpu_usage','show_vram_usage','show_cpu_usage','show_system_usage','font_bold','scroll_tracking','session_context','chinese_translation_via_english','share_translations')
        if key in choices and value not in choices[key]:return
        if key in booleans:value=bool(value)
        elif key=='overlay_opacity':value=max(.3,min(1.,float(value)))
        elif key=='max_font_px':value=max(10,min(96,int(value)))
        elif key not in choices:return
        visual=key in ('panel_theme','overlay_opacity','font_family','max_font_px','font_bold','show_gpu_usage','show_vram_usage','show_cpu_usage')
        if (self.job or self._stopping) and not visual:self.status('İşlem tamamlandıktan sonra ayarı değiştirebilirsiniz.');return
        if self._state['running'] and not visual:self.status('Bu ayarı değiştirmeden önce çeviriyi durdurun.');return
        if self.backend and not visual:
            self.release_backend(lambda:self.setting(key,value));return
        setattr(self.settings,key,value)
        if key in ('show_gpu_usage','show_vram_usage','show_cpu_usage'):
            self.settings.usage_preferences_set=True
        if self.backend and visual:
            setattr(self.backend.s,key,value)
            if key in ('overlay_opacity','font_family','max_font_px','font_bold'):self.backend.overlay.refresh_style()
        if key=="speed_preset":self.settings.apply_preset(value)
        self.settings.save()
        enabled=any((self.settings.show_gpu_usage,self.settings.show_vram_usage,self.settings.show_cpu_usage))
        self.monitor.set_enabled(enabled and self.settings.show_gpu_usage,enabled and self.settings.show_vram_usage,enabled and self.settings.show_cpu_usage)
        self.changed.emit()

    @Slot(str)
    def action(self,name):
        if name=='quit':
            if self.job or self._stopping:self.status('Kurulum işleminin tamamlanmasını bekleyin.');return
            self.release_backend(QApplication.instance().quit);return
        if name=='github':
            QDesktopServices.openUrl(QUrl('https://github.com/tu5j4/mergen'));return
        if self.job or self._stopping:self.status('Devam eden işlemin tamamlanmasını bekleyin.');return
        try:
            if name in ('region','full','overlay','start','once'):
                if name in ('start','once'):
                    missing=service.missing_components(self.settings)
                    if missing:
                        self.status('Önce bu bileşenleri kurun: '+', '.join(missing));self.navigate.emit(2);return
                backend=self.ensure_backend()
                if name=='region':backend.select_region(False)
                elif name=='full':backend._select_fullscreen()
                elif name=='overlay':backend.toggle_overlay_visible()
                elif name=='once':backend.translate_now()
                else:backend.toggle_run()
                self._state['running']=backend.running;self.changed.emit()
            elif name=='recommended':
                profile=getattr(self,'_profile',None)
                if not profile:return
                self._pending=('plan',profile)
                self.confirmation.emit('önerilen bileşenleri kur','bu bileşen ve kütüphaneler internetten indirilecek. birkaç gb alan gerekebilir.')
            elif name=='clear-context':
                if self.backend:self.backend._clear_context()
                else:self.status('Konuşma hafızası boş.')
            elif name=='validate':
                self._state.update(operationTitle='model testi',phase='seçili ortamlar kontrol ediliyor…',validation=[],validationSummary='model testi sürüyor…',progress=0)
                self.navigate.emit(1)
                self.release_backend(lambda:self.start_job(lambda emit:service.validate(self.settings,emit),self.validation_done))
            elif name=='check-update':
                from app.updates import check
                self.start_job(lambda emit:check(),self.update_checked)
            elif name=='update' and self._state['updateAvailable']:
                self._pending=('update',self._update);self.confirmation.emit('Güncelleme','Yeni sürüm indirilecek. Uygulama kapanıp güncellendikten sonra yeniden açılacak.')
        except Exception as exc:self.status(str(exc))

    @Slot(str,str)
    def component(self,operation,key):
        if key not in COMPONENTS or operation not in ('install','remove'):return
        if self.job or self._stopping:return
        self._pending=(operation,key)
        title=COMPONENTS[key]['title']
        text=('bu bileşen ve kütüphaneler internetten indirilecek. birkaç gb alan gerekebilir.' if operation=='install'
              else 'seçili bileşen kaldırılacak. gerektiğinde yeniden indirebilirsin.')
        self.confirmation.emit(title.lower(),text)

    @Slot(bool)
    def confirm(self,accepted):
        pending,self._pending=self._pending,None
        if not accepted or not pending:return
        operation,key=pending
        if operation=='plan':
            def done(report):
                self.settings.translation_backend=key['translation'];self.settings.ocr_backend='cpu';self.settings.manga_backend=key['translation']
                self.settings.use_manga_ocr=False;self.settings.save();self.validation_done(report)
            self._state.update(operationTitle='önerilen bileşenler kuruluyor',phase='kurulum hazırlanıyor…',validation=[],validationSummary='kurulum bitince model testi otomatik çalışacak.',progress=0)
            trial=replace(self.settings,translation_backend=key['translation'],ocr_backend='cpu',manga_backend=key['translation'],use_manga_ocr=False)
            def install_and_test(emit):
                service.install_plan(key,emit)
                return service.validate(trial,emit)
            self.release_backend(lambda:self.start_job(install_and_test,done));return
        if operation=='update':
            from app.updates import download_update, launch_update
            def done(path):self.release_backend(lambda:(launch_update(path),QApplication.instance().quit()))
            self.release_backend(lambda:self.start_job(lambda emit:download_update(key,emit),done));return
        fn=service.install if operation=='install' else service.remove
        self._state.update(operationTitle=COMPONENTS[key]['title'],phase='kuruluyor…' if operation=='install' else 'kaldırılıyor…',activeComponent=key,progress=-1)
        self.release_backend(lambda:self.start_job(lambda emit:fn(key,emit),lambda _:self.component_done()))

    def update_checked(self,result):
        self._update=result
        self._state['updateAvailable']=bool(result.get('available'))
        self._state['updates']=result.get('message','')
        self.changed.emit()


    def component_done(self):
        self._state.update(operationTitle='işlem tamamlandı',phase='bileşen işlemi tamamlandı.',activeComponent='',progress=100)
        self.scan_components();self.status('bileşen işlemi tamamlandı. model testini çalıştırabilirsin.')
