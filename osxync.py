import os
import datetime
import shutil
import socket
import plistlib
import logging

logging.basicConfig(level=logging.INFO)


class AppInstaller(object):
  def __init__(self):
    pass

  def install(self, app):
    print('At some point install %s' % app.name)


class Syncer(object):
  def __init__(self, sync_root, sync_id):
    sync_root = os.path.expanduser(sync_root)
    assert os.path.exists(sync_root)

    self.upload_root = os.path.join(sync_root, sync_id)
    self.upload_backup_root = os.path.join(self.upload_root, 'latest_history')
    self.upload_latest_root = os.path.join(self.upload_root, 'latest')
    self.local_backup_root = os.path.join(self.upload_root, 'local_history_%s' % socket.gethostname())

    self._ensure_dirs([self.upload_root, self.upload_latest_root, self.upload_backup_root, self.local_backup_root])

  def upstream_to_local(self, app, upstream_path=None):
    upstream_path = upstream_path or self.upstream_path(app)
    for p in app.sync_paths():
      dst = os.path.expandvars(os.path.expanduser(p))
      src = os.path.join(upstream_path, self.denormalize_path_string(p))
      self.remove_item(dst)
      self.copy_item(src, dst)

  def local_to_upstream(self, app, upstream_path=None):
    upstream_path = upstream_path or self.upstream_path(app)
    self.remove_item(upstream_path)
    os.mkdir(upstream_path)
    for p in app.sync_paths():
      src = os.path.expandvars(os.path.expanduser(p))
      dst = os.path.join(upstream_path, self.denormalize_path_string(p))
      self.copy_item(src, dst)

  def app_path_token(self, app):
    return app.name

  def denormalize_path_string(self, path):
    path = path.replace('/', '___')
    path = path.replace('~', '__HOME__')
    path = path.replace('%', '__--__')
    return path

  def upstream_path(self, app, upstream_root=None):
    upstream_root = upstream_root or self.upload_latest_root
    return os.path.join(upstream_root, self.app_path_token(app))

  def next_backup_id(self, app, backup_root):
    return datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")

  def exists_upstream(self, app):
    return os.path.exists(self.upstream_path(app))

  def exists_local(self, app):
    return app.exists()

  def create_upstream(self, app):
    self.remove_item(self.upstream_path(app))
    os.mkdir(self.upstream_path(app))


  def is_upstream_newer(self, app):
    lt = self.local_timestamp(app)
    ut = self.upstream_timestamp(app)
    return ut and (not lt or ut > lt)

  def is_local_newer(self, app):
    lt = self.local_timestamp(app)
    ut = self.upstream_timestamp(app)
    return lt and (not ut or lt > ut)

  def upstream_timestamp(self, app):
    t = None
    p = self.upstream_path(app)
    if os.path.exists(p):
      t = self._max_dt(t, self._latest_path_timestamp(p, True))
    return t

  def local_timestamp(self, app):
    t = None
    for p in app.sync_paths():
      p = os.path.expandvars(os.path.expanduser(p))
      if os.path.exists(p):
        t = self._max_dt(t, self._latest_path_timestamp(p))
    return t

  def _latest_path_timestamp(self, path, subonly=False):
    if not os.path.exists(path):
      return None
    t = datetime.datetime.fromtimestamp(os.path.getmtime(path)) if not subonly else None
    if os.path.isdir(path):
      for e in os.listdir(path):
        et = self._latest_path_timestamp(os.path.join(path, e))
        t = self._max_dt(t, et)
    return t

  def _max_dt(self, a, b):
    if a is None: return b
    if b is None: return a
    return max(a, b)

  def _ensure_dirs(self, dirs):
    for d in dirs:
      if not os.path.exists(d):
        os.mkdir(d)

  def should_upload(self, app):
    if not self.exists_local(app):
      return False
    if not self.exists_upstream(app):
      return True
    if self.is_local_newer(app):
      return True

  def should_download(self, app):
    if not self.exists_local(app):
      return False
    if not self.exists_upstream(app):
      return False
    if self.is_upstream_newer(app):
      return True

  def backup_upstream_copy(self, app):
    backup_path = self.upstream_path(app, self.upload_backup_root)
    backup_id = self.next_backup_id(app, backup_path)
    backup_path = os.path.join(backup_path, backup_id)
    src_path = self.upstream_path(app)
    assert os.path.exists(src_path)
    self.remove_item(backup_path)
    self.copy_item(src_path, backup_path)

  def backup_local_copy(self, app):
    backup_path = self.upstream_path(app, self.local_backup_root)
    backup_id = self.next_backup_id(app, backup_path)
    backup_path = os.path.join(backup_path, backup_id)
    self.local_to_upstream(app, backup_path)

  def copy_item(self, src_path, dst_path, skip_missing=True):
    if skip_missing and not os.path.exists(src_path):
      return
    assert os.path.exists(src_path)
    if os.path.isdir(src_path):
      shutil.copytree(src_path, dst_path)
    else:
      shutil.copy2(src_path, dst_path)

  def remove_item(self, path):
    if os.path.exists(path):
      if os.path.isdir(path):
        shutil.rmtree(path)
      else:
        os.remove(path)

  def save_apps(self, sync_apps, install_apps):
    pass

  def get_sync_apps(self):
    pass

  def get_install_apps(self):
    pass

  def sync(self, installed_apps, apps):
    apps = apps or self.read_apps_to_sync()
    for app in apps:
      if app in installed_apps:
        logging.info('%s: Installed', app.name)
        app = installed_apps[app]
        if self.should_upload(app):
          logging.info('%s: Needs push to upstream', app.name)
          if self.exists_upstream(app):
            logging.info('%s: Backing up existing upstream copy', app.name)
            self.backup_upstream_copy(app)
          logging.info('%s: Pushing local copy to upstream', app.name)
          app.local_to_upstream(self)
        elif self.should_download(app):
          logging.info('%s: Needs pull to local', app.name)
          if self.exists_local(app):
            logging.info('%s: Backing up existing local copy', app.name)
            self.backup_local_copy(app)
          logging.info('%s: Pushing upstream copy to local', app.name)
          app.upstream_to_local(self)
        else:
          logging.info('%s: Nothing to do', app.name)
          pass
        logging.info('%s: Done', app.name)
      else:
        logging.info('%s: Not installed', app.name)


class App(object):
  DefaultAppRoots = []

  def __init__(self, name, app_roots=None, identifier=None, full_path=None, app_path=None, sync_paths=None,
               sync_exclude_patterns=None,
               installer=None):
    self.name = name
    self.app_roots = app_roots if app_roots is not None else App.DefaultAppRoots
    self.app_path = app_path or '%s.app' % self.name
    self.identifier = identifier
    self.full_path = full_path or self.find_full_path()
    self.installer = installer
    self.sync_exclude_patterns = sync_exclude_patterns or []

    if self.identifier is None and self.full_path:
      self.identifier = App.bundle_identifier(self.full_path)

    self._hash = hash((self.name, self.identifier or ''))
    self._sync_paths = sync_paths

  def __eq__(self, obj):
    return isinstance(obj, App) and obj.name == self.name and (
      (not obj.identifier and not self.identifier) or (obj.identifier == self.identifier))

  def __ne__(self, obj):
    return not self == obj

  def __hash__(self):
    return self._hash

  def __repr__(self):
    return '%s<%s>' % (self.name, self.__class__.__name__)

  def sync_paths(self):
    sync_paths = []
    if not self._sync_paths is None:
      sync_paths = list(self._sync_paths)
    else:
      sync_paths.append('~/Library/Application Support/%s' % self.name)
      if self.identifier:
        sync_paths.append('~/Library/Preferences/%s' % self.identifier)
        sync_paths.append('~/Library/Preferences/%s.plist' % self.identifier)
      self._sync_paths = sync_paths
    return sync_paths

  @classmethod
  def bundle_identifier(cls, app_path):
    plist = os.path.join(app_path, 'Contents/Info.plist')
    if os.path.exists(plist):
      plist = plistlib.readPlist(plist)
      return plist.get('CFBundleIdentifier')
    return None

  def find_full_path(self):
    for root in self.app_roots:
      path = root.exists(self.app_path)
      if path:
        if self.identifier:
          bi = App.bundle_identifier(path)
          if self.identifier == bi:
            return path
        else:
          return path
    return None

  def exists(self):
    return self.full_path is not None

  def local_to_upstream(self, syncher):
    return syncher.local_to_upstream(self)

  def upstream_to_local(self, syncher):
    return syncher.upstream_to_local(self)


class AppRoot(object):
  def __init__(self, path, recursive=False):
    self.path = path
    self.recursive = recursive

  def apps(self):
    return self._apps_in_path(self.path, self.recursive)

  def exists(self, sub_path):
    fp = os.path.join(self.path, sub_path)
    return fp if os.path.exists(fp) else None

  def _apps_in_path(self, path, recursive):
    for e in os.listdir(os.path.join(self.path, path)):
      if os.path.isdir(os.path.join(self.path, path, e)):
        if e.endswith('.app'):
          yield App(os.path.splitext(e)[0], full_path=os.path.join(path, e))
        elif recursive:
          yield from self._apps_in_path(os.path.join(path, e))


APP_ROOTS = [
  AppRoot('/Applications')
]
App.DefaultAppRoots = APP_ROOTS

KNOWN_APPS = {
  App('iTerm', identifier='com.googlecode.iterm2'),
  App('PyCharm', identifier='com.jetbrains.pycharm', sync_paths=[
    '~/Library/Preferences/com.jetbrains.pycharm.plist',
    '~/Library/Application Support/PyCharm30',
    '~/Library/Application Support/PyCharm40',
  ]),
}
KNOWN_APPS = dict(zip(KNOWN_APPS, KNOWN_APPS))

DISCOVERED_APPS = [

]

INSTALLED_APPS = [

]

ALL_APPS = [

]

SYNC_APPS = [
  App('iTerm'),
  App('PyCharm'),
]

WORK_APPS = [

]


def main():
  s = Syncer('~/Google Drive/osxync', '1')

  # for app in KNOWN_APPS:
  # if app.exists():
  #     INSTALLED_APPS.append(app)
  #
  # for root in APP_ROOTS:
  #   for a in root.apps():
  #     if a not in KNOWN_APPS:
  #       DISCOVERED_APPS.append(a)
  #
  # ALL_APPS.extend(INSTALLED_APPS)
  # ALL_APPS.extend(DISCOVERED_APPS)
  #
  # WORK_APPS = [app for app in ALL_APPS if app in SYNC_APPS]

  s.sync(KNOWN_APPS, SYNC_APPS)


if __name__ == '__main__':
  main()
