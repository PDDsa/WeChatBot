#!/usr/bin/env python3
# coding=utf-8

import requests
import pyqrcode
import webbrowser
import xml.dom.minidom
import json
#import pdb
import traceback
import time, random, re, sys, os


class SafeSession(requests.Session):
    def request(self, method, url, params=None, data=None, headers=None, cookies=None, files=None, auth=None,
                timeout=None, allow_redirects=True, proxies=None, hooks=None, stream=None, verify=None, cert=None,
                json=None):
        for i in range(3):
            try:
                return super(SafeSession, self).request(method, url, params, data, headers, cookies, files, auth,
                                                        timeout,
                                                        allow_redirects, proxies, hooks, stream, verify, cert, json)
            except Exception as e:
                print(e.message, traceback.format_exc())
                continue

        #重试3次以后再加一次，抛出异常
        try:
            return super(SafeSession, self).request(method, url, params, data, headers, cookies, files, auth,
                                                    timeout,
                                                    allow_redirects, proxies, hooks, stream, verify, cert, json)
        except Exception as e:
            raise e

class WeChat:
    '''
    微信web接口二次开发
    '''
    def __init__(self):
        self.session = SafeSession()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux i686; U;) Gecko/20070322 Kazehakase/0.4.5'})
        self.conf = {'qr':'tty'}
        self.uuid = ''

        self.redirect_uri = ''
        self.base_uri = ''
        self.base_host = ''

        self.skey = ''
        self.sid = ''
        self.uin = ''
        self.device_id = 'e' + repr(random.random())[2:17]
        self.pass_ticket = ''
        self.base_request = {}
        self.my_account = {}  # 当前账户
        self.is_big_contact = False
        # 所有相关账号: 联系人, 公众号, 群组, 特殊账号
        self.member_list = []

        # 所有群组的成员, {'group_id1': [member1, member2, ...], ...}
        self.group_members = {}

        # 所有账户, {'group_member':{'id':{'type':'group_member', 'info':{}}, ...}, 'normal_member':{'id':{}, ...}}
        self.account_info = {'group_member': {}, 'normal_member': {}}

        self.contact_list = []  # 联系人列表
        self.public_list = []  # 公众账号列表
        self.group_list = []  # 群聊列表
        self.special_list = []  # 特殊账号列表
        self.encry_chat_room_id_list = []  # 存储群聊的EncryChatRoomId，获取群内成员头像时需要用到

        self.file_index = 0

        self.UNKONWN = 'unkonwn'
        self.SUCCESS = '200'
        self.SCANED = '201'
        self.TIMEOUT = '408'

        #文件缓存目录
        self.temp_pwd  =  os.path.join(os.getcwd(),'temp')
        if os.path.exists(self.temp_pwd) == False:
            os.makedirs(self.temp_pwd)

        self.DEBUG = False

    def get_uuid(self):
        url = 'https://login.weixin.qq.com/jslogin'
        params = {
            'appid': 'wx782c26e4c19acffb',
            'fun': 'new',
            'lang': 'zh_CN',
            '_': int(time.time()) * 1000 + random.randint(1, 999),
        }
        r = self.session.get(url,params=params)
        print(r.url)
        print(r.text)
        data = r.text
        regx = r'window.QRLogin.code = (\d+); window.QRLogin.uuid = "(\S+?)"'
        pm = re.search(regx, data)
        if pm:
            code = pm.group(1)
            self.uuid = pm.group(2)
            print(code)
            print(self.uuid)
            return code == '200'
        return False

    def gen_qr_code(self, qr_file_path):
        string = 'https://login.weixin.qq.com/l/' + self.uuid
        qr = pyqrcode.create(string)
        if self.conf['qr'] == 'png':
            qr.png(qr_file_path, scale=5)
            self.show_image(qr_file_path)
            # img = Image.open(qr_file_path)
            # img.show()
        elif self.conf['qr'] == 'tty':
            print(qr.terminal(quiet_zone=1))

    def show_image(self,file_path):
        """
        跨平台显示图片文件
        :param file_path: 图片文件路径
        """
        if sys.version_info >= (3, 3):
            from shlex import quote
        else:
            from pipes import quote

        if sys.platform == "darwin":
            command = "open -a /Applications/Preview.app %s&" % quote(file_path)
            os.system(command)
        else:
            webbrowser.open(file_path)

    def wait4login(self):
        """
        http comet:
        tip=1, 等待用户扫描二维码,
               201: scaned
               408: timeout
        tip=0, 等待用户确认登录,
               200: confirmed
        """
        LOGIN_TEMPLATE = 'https://login.weixin.qq.com/cgi-bin/mmwebwx-bin/login?tip=%s&uuid=%s&_=%s'
        tip = 1

        try_later_secs = 1
        MAX_RETRY_TIMES = 10

        code = self.UNKONWN

        retry_time = MAX_RETRY_TIMES
        while retry_time > 0:
            url = LOGIN_TEMPLATE % (tip, self.uuid, int(time.time()))
            code, data = self.do_request(url)
            if code == self.SCANED:
                print('[INFO] Please confirm to login .')
                tip = 0
            elif code == self.SUCCESS:  # 确认登录成功
                param = re.search(r'window.redirect_uri="(\S+?)";', data)
                redirect_uri = param.group(1) + '&fun=new'
                self.redirect_uri = redirect_uri
                self.base_uri = redirect_uri[:redirect_uri.rfind('/')]
                temp_host = self.base_uri[8:]
                self.base_host = temp_host[:temp_host.find("/")]
                return code
            elif code == self.TIMEOUT:
                print('[ERROR] WeChat login timeout. retry in %s secs later...' % (try_later_secs,))

                tip = 1  # 重置
                retry_time -= 1
                time.sleep(try_later_secs)
            else:
                print (('[ERROR] WeChat login exception return_code=%s. retry in %s secs later...' %
                       (code, try_later_secs)))
                tip = 1
                retry_time -= 1
                time.sleep(try_later_secs)
        return code

    def do_request(self, url):
        r =self.session.get(url)
        r.encoding = 'utf-8'
        data = r.text
        param = re.search(r'window.code=(\d+);', data)
        code = param.group(1)
        return code, data

    def login(self):
        if len(self.redirect_uri) < 4:
            print('[ERROR] Login failed due to network problem, please try again.')
            return False
        r =self.session.get(self.redirect_uri)
        r.encoding = 'utf-8'
        data = r.text
        doc = xml.dom.minidom.parseString(data)
        root = doc.documentElement

        for node in root.childNodes:
            if node.nodeName == 'skey':
                self.skey = node.childNodes[0].data
            elif node.nodeName == 'wxsid':
                self.sid = node.childNodes[0].data
            elif node.nodeName == 'wxuin':
                self.uin = node.childNodes[0].data
            elif node.nodeName == 'pass_ticket':
                self.pass_ticket = node.childNodes[0].data

        if '' in (self.skey, self.sid, self.uin, self.pass_ticket):
            return False

        self.base_request = {
            'Uin': self.uin,
            'Sid': self.sid,
            'Skey': self.skey,
            'DeviceID': self.device_id,
        }
        return True


    def init(self):
        url = self.base_uri + '/webwxinit?r=%i&lang=en_US&pass_ticket=%s' % (int(time.time()), self.pass_ticket)
        params = {
            'BaseRequest': self.base_request
        }
        r =self.session.post(url, data=json.dumps(params))
        r.encoding = 'utf-8'
        dic = json.loads(r.text)
        self.sync_key = dic['SyncKey']
        self.my_account = dic['User']
        self.sync_key_str = '|'.join([str(keyVal['Key']) + '_' + str(keyVal['Val'])
                                      for keyVal in self.sync_key['List']])
        return dic['BaseResponse']['Ret'] == 0


    def status_notify(self):
        url = self.base_uri + '/webwxstatusnotify?lang=zh_CN&pass_ticket=%s' % self.pass_ticket
        self.base_request['Uin'] = int(self.base_request['Uin'])
        params = {
            'BaseRequest': self.base_request,
            "Code": 3,
            "FromUserName": self.my_account['UserName'],
            "ToUserName": self.my_account['UserName'],
            "ClientMsgId": int(time.time())
        }
        r =self.session.post(url, data=json.dumps(params))
        r.encoding = 'utf-8'
        dic = json.loads(r.text)
        return dic['BaseResponse']['Ret'] == 0

    def get_contact(self):
        """获取当前账户的所有相关账号(包括联系人、公众号、群聊、特殊账号)"""
        if self.is_big_contact:
            return False
        url = self.base_uri + '/webwxgetcontact?pass_ticket=%s&skey=%s&r=%s' \
                              % (self.pass_ticket, self.skey, int(time.time()))
        #pdb.set_trace() # 运行到这里会自动暂停
        #如果通讯录联系人过多，这里会直接获取失败
        try:
            r = self.session.post(url, data='{}')
        except:
            self.is_big_contact = True
            return False
        r.encoding = 'utf-8'
        if self.DEBUG:
            with open(os.path.join(self.temp_pwd,'contacts.json'), 'w') as f:
                f.write(r.text.encode('utf-8'))
        dic = json.loads(r.text)
        self.member_list = dic['MemberList']

        special_users = ['newsapp', 'fmessage', 'filehelper', 'weibo', 'qqmail',
                         'fmessage', 'tmessage', 'qmessage', 'qqsync', 'floatbottle',
                         'lbsapp', 'shakeapp', 'medianote', 'qqfriend', 'readerapp',
                         'blogapp', 'facebookapp', 'masssendapp', 'meishiapp',
                         'feedsapp', 'voip', 'blogappweixin', 'weixin', 'brandsessionholder',
                         'weixinreminder', 'wxid_novlwrv3lqwv11', 'gh_22b87fa7cb3c',
                         'officialaccounts', 'notification_messages', 'wxid_novlwrv3lqwv11',
                         'gh_22b87fa7cb3c', 'wxitil', 'userexperience_alarm', 'notification_messages']

        self.contact_list = []
        self.public_list = []
        self.special_list = []
        self.group_list = []

        for contact in self.member_list:
            if contact['VerifyFlag'] & 8 != 0:  # 公众号
                self.public_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'public', 'info': contact}
            elif contact['UserName'] in special_users:  # 特殊账户
                self.special_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'special', 'info': contact}
            elif contact['UserName'].find('@@') != -1:  # 群聊
                self.group_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'group', 'info': contact}
            elif contact['UserName'] == self.my_account['UserName']:  # 自己
                self.account_info['normal_member'][contact['UserName']] = {'type': 'self', 'info': contact}
            else:
                self.contact_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'contact', 'info': contact}

        self.batch_get_group_members()

        for group in self.group_members:
            for member in self.group_members[group]:
                if member['UserName'] not in self.account_info:
                    self.account_info['group_member'][member['UserName']] = \
                        {'type': 'group_member', 'info': member, 'group': group}

        if self.DEBUG:
            with open(os.path.join(self.temp_pwd,'contact_list.json'), 'w') as f:
                f.write(json.dumps(self.contact_list))
            with open(os.path.join(self.temp_pwd,'special_list.json'), 'w') as f:
                f.write(json.dumps(self.special_list))
            with open(os.path.join(self.temp_pwd,'group_list.json'), 'w') as f:
                f.write(json.dumps(self.group_list))
            with open(os.path.join(self.temp_pwd,'public_list.json'), 'w') as f:
                f.write(json.dumps(self.public_list))
            with open(os.path.join(self.temp_pwd,'member_list.json'), 'w') as f:
                f.write(json.dumps(self.member_list))
            with open(os.path.join(self.temp_pwd,'group_users.json'), 'w') as f:
                f.write(json.dumps(self.group_members))
            with open(os.path.join(self.temp_pwd,'account_info.json'), 'w') as f:
                f.write(json.dumps(self.account_info))
        return True

    def batch_get_group_members(self):
        """批量获取所有群聊成员信息"""
        url = self.base_uri + '/webwxbatchgetcontact?type=ex&r=%s&pass_ticket=%s' % (int(time.time()), self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            "Count": len(self.group_list),
            "List": [{"UserName": group['UserName'], "EncryChatRoomId": ""} for group in self.group_list]
        }
        r =self.session.post(url, data=json.dumps(params))
        r.encoding = 'utf-8'
        dic = json.loads(r.text)
        group_members = {}
        encry_chat_room_id = {}
        for group in dic['ContactList']:
            gid = group['UserName']
            members = group['MemberList']
            group_members[gid] = members
            encry_chat_room_id[gid] = group['EncryChatRoomId']
        self.group_members = group_members
        self.encry_chat_room_id_list = encry_chat_room_id


    def run(self):
        self.get_uuid()
        self.gen_qr_code(os.path.join(self.temp_pwd,'wxqr.png'))
        print('[INFO] Please use WeChat to scan the QR code .')
        result =self.wait4login()
        if result != wechat.SUCCESS:
            print('[ERROR] Web WeChat login failed. failed code=%s' % (result))
            return

        if wechat.login():
            print('[INFO] Web WeChat login succeed .')
        else:
            print('[ERROR] Web WeChat login failed .')
            return
        if wechat.init():
            print('[INFO] Web WeChat init succeed .')
        else:
            print('[INFO] Web WeChat init failed')
            return
        self.status_notify()
        if self.get_contact():
            print('[INFO] Get %d contacts' % len(self.contact_list))
            print('[INFO] Start to process messages .')

if __name__=='__main__':
    wechat = WeChat()
    wechat.run()
    print(wechat.my_account)
