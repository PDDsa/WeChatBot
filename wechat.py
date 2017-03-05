#!/usr/bin/env python3
# coding=utf-8

import requests
import pyqrcode
import webbrowser
import xml.dom.minidom
import json
import time, random, re, sys, os

class WeChat:
    '''
    微信web接口二次开发
    '''
    def __init__(self):
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
        # 所有相关账号: 联系人, 公众号, 群组, 特殊账号
        self.member_list = []

        self.UNKONWN = 'unkonwn'
        self.SUCCESS = '200'
        self.SCANED = '201'
        self.TIMEOUT = '408'

        #文件缓存目录
        self.temp_pwd  =  os.path.join(os.getcwd(),'temp')
        if os.path.exists(self.temp_pwd) == False:
            os.makedirs(self.temp_pwd)

    def get_uuid(self):
        url = 'https://login.weixin.qq.com/jslogin'
        params = {
            'appid': 'wx782c26e4c19acffb',
            'fun': 'new',
            'lang': 'zh_CN',
            '_': int(time.time()) * 1000 + random.randint(1, 999),
        }
        r = requests.get(url,params=params)
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

    @staticmethod
    def show_image(file_path):
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
            webbrowser.open(os.path.join(os.getcwd(),file_path))

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
        r = requests.get(url)
        r.encoding = 'utf-8'
        data = r.text
        param = re.search(r'window.code=(\d+);', data)
        code = param.group(1)
        return code, data

    def login(self):
        if len(self.redirect_uri) < 4:
            print('[ERROR] Login failed due to network problem, please try again.')
            return False
        r = requests.get(self.redirect_uri)
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
        r = requests.post(url, data=json.dumps(params))
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
        r = requests.post(url, data=json.dumps(params))
        r.encoding = 'utf-8'
        dic = json.loads(r.text)
        return dic['BaseResponse']['Ret'] == 0


    def run(self):
        self.get_uuid()
        self.gen_qr_code('temp/wxqr.png')
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

if __name__=='__main__':
    wechat = WeChat()
    wechat.run()
    print(wechat.my_account)
