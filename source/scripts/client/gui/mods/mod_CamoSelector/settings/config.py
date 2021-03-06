# coding=utf-8
import BigWorld
import ResMgr
import items.vehicles
import nations
import os
import traceback
from CurrentVehicle import g_currentPreviewVehicle, g_currentVehicle
from PYmodsCore import PYmodsConfigInterface, loadJson, refreshCurrentVehicle, remDups, Analytics
from gui.Scaleform.framework.managers.loaders import ViewLoadParams
from gui.Scaleform.genConsts.SEASONS_CONSTANTS import SEASONS_CONSTANTS
from gui.app_loader import g_appLoader
from items.components.c11n_constants import SeasonType
from .shared import RandMode, getCamoTextureName
from .. import __date__, __modID__


class ConfigInterface(PYmodsConfigInterface):
    def __init__(self):
        self.disable = []
        self.camoForSeason = {}
        self.arenaCamoCache = {}
        self.hangarCamoCache = {}
        self.outfitCache = {}
        self.camouflages = {}
        self.configFolders = {}
        self.teamCamo = dict.fromkeys(('ally', 'enemy'))
        self.interCamo = []
        self.isModAdded = False
        super(ConfigInterface, self).__init__()

    def init(self):
        self.ID = __modID__
        self.version = '2.1.0 (%s)' % __date__
        self.author += ' (thx to tratatank, Blither!)'
        self.data = {'enabled': True, 'doRandom': True, 'useBought': True, 'hangarCamoKind': 0,
                     'fullAlpha': False, 'disableWithDefault': False, 'fillEmptySlots': True, 'uniformOutfit': False}
        self.i18n = {
            'UI_description': 'Camouflage selector',
            'UI_flash_header': 'Camouflages setup',
            'UI_flash_header_tooltip': ('Advanced settings for camouflages added by CamoSelector by '
                                        '<font color=\'#DD7700\'><b>Polyacov_Yury</b></font>'),
            'UI_flash_tabs_0_label': 'Paint',
            'UI_flashCol_tabs_0_text': 'Paint',
            'UI_flashCol_tabs_0_tooltip': 'Not camouflages at all. Paints. :)',
            'UI_flash_tabs_1_label': 'Shop',
            'UI_flashCol_tabs_1_text': 'Shop',
            'UI_flashCol_tabs_1_tooltip': 'Those which can be bought normally.',
            'UI_flash_tabs_2_label': 'Hidden',
            'UI_flashCol_tabs_2_text': 'Hidden',
            'UI_flashCol_tabs_2_tooltip': 'Those which are inaccessible under usual circumstances.',
            'UI_flash_tabs_3_label': 'Global',
            'UI_flashCol_tabs_3_text': 'Global map',
            'UI_flashCol_tabs_3_tooltip':
                'Those which are awarded for global map achievements, thus available for all nations.',
            'UI_flash_tabs_4_label': 'Custom',
            'UI_flashCol_tabs_4_text': 'Custom',
            'UI_flashCol_tabs_4_tooltip': 'Those which were added via config files.',
            'UI_flash_tabs_5_label': 'Emblems',
            'UI_flashCol_tabs_5_text': 'Emblems',
            'UI_flashCol_tabs_5_tooltip': 'Those small pictures that are added on your machine in place of nation flags.',
            'UI_flash_tabs_6_label': 'Inscriptions',
            'UI_flashCol_tabs_6_text': 'Inscriptions',
            'UI_flashCol_tabs_6_tooltip': 'Looks like chat is not enough.',
            'UI_flash_tabs_7_label': 'Effects',
            'UI_flashCol_tabs_7_text': 'Effects',
            'UI_flashCol_tabs_7_tooltip': 'Also known as paint scrambles.',
            'UI_flash_switcher_setup': 'SETUP',
            'UI_flash_switcher_install': 'INSTALL',
            'UI_flash_commit_apply': 'Apply',
            'UI_flash_commit_install': 'Install',
            'UI_flash_commit_install_and_apply': 'Install and apply',
            'UI_flashCol_randMode_label': 'Random selection mode',
            'UI_flash_randMode_off': 'Disable',
            'UI_flash_randMode_random': 'Random',
            'UI_flash_randMode_team': 'Team',
            'UI_flashCol_teamMode_label': 'Use for team',
            'UI_flash_teamMode_ally': 'Ally',
            'UI_flash_teamMode_enemy': 'Enemy',
            'UI_flash_teamMode_both': 'All',
            'UI_flashCol_camoGroup_multinational': 'Multinational',
            'UI_flashCol_camoGroup_special': 'Special',
            'UI_flashCol_camoGroup_custom': 'Custom',
            'UI_flashCol_applied_money': 'Customization elements applied.\nWould buy %(count)s items, would spend %(money)s.',
            'UI_setting_doRandom_text': 'Select random camouflages',
            'UI_setting_doRandom_tooltip': (
                'If enabled, mod will select a random available camouflage if no other option is provided.'),
            'UI_setting_useBought_text': 'Use bought camouflages in battle',
            'UI_setting_useBought_tooltip': "If enabled, mod will preserve bought camouflages on other players' tanks.",
            'UI_setting_disableWithDefault_text': 'Disable for vehicles with default camouflage',
            'UI_setting_disableWithDefault_tooltip': 'If enabled, mod will ignore vehicles with a default camouflage.',
            'UI_setting_fullAlpha_text': 'Non-transparent custom camouflages',
            'UI_setting_fullAlpha_tooltip': 'If enabled, all custom camouflages lose their transparency.\n'
                                            'Some call this "dirt-less skins".',
            'UI_setting_fillEmptySlots_text': 'Fill empty slots',
            'UI_setting_fillEmptySlots_tooltip': 'Add random camouflages if a vehicle has empty slots for them.',
            'UI_setting_uniformOutfit_text': 'Same look for all parts',
            'UI_setting_uniformOutfit_tooltip':
                'Random camouflages are picked up so that a vehicle has the same camouflage on all parts (if possible).',
            'UI_setting_hangarCamoKind_text': 'Hangar camouflage season',
            'UI_setting_hangarCamoKind_tooltip': 'This setting controls the season which is used in hangar.',
            'UI_setting_hangarCamo_winter': 'Winter', 'UI_setting_hangarCamo_summer': 'Summer',
            'UI_setting_hangarCamo_desert': 'Desert', 'UI_setting_hangarCamo_random': 'Random'}
        super(ConfigInterface, self).init()

    def loadLang(self):
        super(ConfigInterface, self).loadLang()
        try:
            from helpers.i18n.hangarpainter import _config
            for key in self.i18n:
                if not key.startswith('UI_flashCol_'):
                    continue
                self.i18n[key] = "<font color='#%s'>%s</font>" % (_config.data['colour'], self.i18n[key])
        except ImportError:
            pass

    def createTemplate(self):
        return {'modDisplayName': self.i18n['UI_description'],
                'settingsVersion': 200,
                'enabled': self.data['enabled'],
                'column1': [self.tb.createOptions('hangarCamoKind', [self.i18n['UI_setting_hangarCamo_' + x] for x in
                                                                     ('winter', 'summer', 'desert', 'random')]),
                            self.tb.createControl('doRandom'),
                            self.tb.createControl('disableWithDefault')],
                'column2': [self.tb.createControl('fillEmptySlots'),
                            self.tb.createControl('uniformOutfit'),
                            self.tb.createControl('useBought'),
                            self.tb.createControl('fullAlpha')]}

    def onMSADestroy(self):
        try:
            from gui.mods import mod_remodenabler
        except ImportError:
            refreshCurrentVehicle()

    def onApplySettings(self, settings):
        if 'fullAlpha' in settings and settings['fullAlpha'] != self.data['fullAlpha']:
            items.vehicles.g_cache._Cache__customization20 = None
            items.vehicles.g_cache.customization20()
        super(self.__class__, self).onApplySettings(settings)
        self.hangarCamoCache.clear()
        if self.isModAdded:
            kwargs = dict(id='CamoSelectorUI', enabled=self.data['enabled'])
            try:
                BigWorld.g_modsListApi.updateModification(**kwargs)
            except AttributeError:
                BigWorld.g_modsListApi.updateMod(**kwargs)

    def readCurrentSettings(self, quiet=True):
        super(ConfigInterface, self).readCurrentSettings(quiet)
        self.configFolders.clear()
        self.camouflages = {'remap': {}, 'custom': {}}
        self.outfitCache = loadJson(self.ID, 'outfitCache', self.outfitCache, self.configPath)
        if os.path.isfile(self.configPath + 'camouflagesCache.json'):
            camouflagesCache = loadJson(self.ID, 'camouflagesCache', {}, self.configPath)
            for nat in camouflagesCache:
                for vehName in camouflagesCache[nat]:
                    for season in camouflagesCache[nat][vehName]:
                        self.outfitCache.setdefault(nat, {}).setdefault(vehName, {}).setdefault(season, {})['camo'] = \
                            camouflagesCache[nat][vehName][season]
            os.remove(self.configPath + 'camouflagesCache.json')
            loadJson(self.ID, 'outfitCache', self.outfitCache, self.configPath, True)
        try:
            camoDirPath = '../' + self.configPath + 'camouflages'
            camoDirSect = ResMgr.openSection(camoDirPath)
            for camoName in remDups(
                    (x for x in camoDirSect.keys() if ResMgr.isDir(camoDirPath + '/' + x))
                    if camoDirSect is not None else []):
                self.configFolders[camoName] = confFolder = set()
                fileName = self.configPath + 'camouflages/' + camoName + '/'
                settings = loadJson(self.ID, 'settings', {}, fileName)
                for key in settings:
                    conf = settings[key]
                    if 'kinds' in conf:
                        conf['season'] = conf['kinds']
                        del conf['kinds']
                    if 'season' in conf:
                        seasonNames = [x for x in conf['season'].split(',') if x]
                        seasonType = SeasonType.UNDEFINED
                        for season in seasonNames:
                            if season in SEASONS_CONSTANTS.SEASONS:
                                seasonType |= getattr(SeasonType, season.upper())
                            else:
                                print self.ID + ': unknown season name for camouflage', key + ':', season
                                conf['season'] = conf['season'].replace(season, '')
                        while ',,' in conf['season']:
                            conf['season'] = conf['season'].replace(',,', ',')
                    else:
                        conf['season'] = ','.join(SEASONS_CONSTANTS.SEASONS)
                    confFolder.add(key)
                self.camouflages['custom'].update(settings)
                loadJson(self.ID, 'settings', settings, fileName, True)
        except StandardError:
            traceback.print_exc()
        camouflages = items.vehicles.g_cache.customization20().camouflages
        camoNames = {id: getCamoTextureName(x) for id, x in camouflages.iteritems() if 'custom' not in x.priceGroupTags}
        camoIndices = {}
        for camoID, camoName in camoNames.iteritems():
            camoIndices.setdefault(camoName, []).append(camoID)
        self.interCamo = []
        for camoName, indices in camoIndices.iteritems():
            nationsList = []
            for ID in indices:
                for filterNode in camouflages[ID].filter.include:
                    if filterNode.nations:
                        nationsList += filterNode.nations
            if set(nationsList) >= set(idx for idx, name in enumerate(nations.NAMES) if name != 'italy'):
                self.interCamo.append(camoName)
        settings = loadJson(self.ID, 'settings', {}, self.configPath)
        if 'disable' in settings:
            if not settings['disable']:
                del settings['disable']
            else:
                self.disable = settings['disable']
        if 'remap' in settings:
            conf = settings['remap']
            for camoName in conf.keys():
                try:
                    camoName = int(camoName)
                except ValueError:
                    if camoName not in camoIndices:
                        print self.ID + ': unknown camouflage for remapping:', camoName
                    else:
                        for camoID in camoIndices[camoName]:
                            conf[camoID] = conf[camoName].copy()
                    del conf[camoName]
                    continue
                if camoName not in camoNames:
                    print self.ID + ': unknown camouflage for remapping:', camoName
                    del conf[str(camoName)]
                else:
                    conf[camoName] = conf.pop(str(camoName))
            for camoID, camouflage in camouflages.items():
                if camoID not in conf:
                    continue
                camoConf = conf[camoID]
                if camoConf.get('random_mode') == RandMode.RANDOM:
                    del camoConf['random_mode']
                if 'kinds' in camoConf:
                    camoConf['season'] = camoConf['kinds']
                    del camoConf['kinds']
                if 'season' in camoConf:
                    seasonNames = [x for x in camoConf['season'].split(',') if x]
                    seasonType = SeasonType.UNDEFINED
                    for season in seasonNames:
                        if season in SEASONS_CONSTANTS.SEASONS:
                            seasonType |= getattr(SeasonType, season.upper())
                        else:
                            print self.ID + ': unknown season name for camouflage', camoID + ':', season
                            camoConf['season'] = camoConf['season'].replace(season, '')
                    while ',,' in camoConf['season']:
                        camoConf['season'] = camoConf['season'].replace(',,', ',')
                    if seasonType == camouflage.season:
                        del camoConf['season']
                for team in ('Ally', 'Enemy'):
                    if camoConf.get('useFor' + team):
                        del camoConf['useFor' + team]
                if not camoConf:
                    del conf[camoID]
            self.camouflages['remap'] = conf
        newSettings = {}
        if self.disable:
            newSettings['disable'] = self.disable
        newSettings['remap'] = settings.get('remap', {})
        loadJson(self.ID, 'settings', newSettings, self.configPath, True)

    def registerSettings(self):
        super(self.__class__, self).registerSettings()
        if hasattr(BigWorld, 'g_modsListApi'):
            kwargs = dict(
                id='CamoSelectorUI', name=self.i18n['UI_flash_header'], description=self.i18n['UI_flash_header_tooltip'],
                icon='gui/flash/CamoSelector.png', enabled=self.data['enabled'], login=False, lobby=True,
                callback=lambda: None if g_currentVehicle.isInBattle() or g_currentPreviewVehicle.isPresent() else (
                    self.onMSAPopulate(), g_appLoader.getDefLobbyApp().loadView(ViewLoadParams('CamoSelectorMainView'))))
            try:
                BigWorld.g_modsListApi.addModification(**kwargs)
            except AttributeError:
                BigWorld.g_modsListApi.addMod(**kwargs)
            self.isModAdded = True


g_config = ConfigInterface()
statistic_mod = Analytics(g_config.ID, g_config.version, 'UA-76792179-7', g_config.configFolders)
