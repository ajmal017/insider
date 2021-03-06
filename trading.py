import aiohttp
import asyncio
import concurrent
import async_timeout
import bs4
from utils import Connection
from connectors import StoreManager, Period, FileType
import time
import socket
import json
import boto3
from analytics import DecisionEngine


class EdgarParams(object):
    def __init__(self):
        self.Url = ''
        self.PageSize = ''
        self.Timeout = 10
        self.StartYear = ''


class EdgarClient:
    """Edgar client."""

    def __init__(self, params, logger, loop=None):
        self.__timeout = params.Timeout
        self.__logger = logger
        self.__params = params
        self.__tokens = None
        self.__loop = loop if loop is not None else asyncio.get_event_loop()

    @Connection.ioreliablehttp
    async def GetTransactionsByOwner(self, cik, path=None):
        # https://www.sec.gov/cgi-bin/own-disp
        def LookupOwners():
            lines = [tr for table in soup.find_all('table')
                     for tr in table.children if isinstance(tr, bs4.Tag)
                     and 'Type of Owner' in tr.parent.text and len(tr.contents) == 8]

            lookup = {}
            for i in lines:
                owner_cik = str(i.contents[2].text)
                owner_type = str(i.contents[6].text)
                lookup[owner_cik] = owner_type
            return lookup

        def GetText(tag):
            nxt = tag.next
            while type(nxt) is not bs4.element.NavigableString:
                nxt = nxt.next
            return nxt

        try:
            transactions = []
            statuses = []
            response = None
            path = path if path is not None else \
                'action=getowner&CIK=%s' % cik
            url = '%s/cgi-bin/own-disp?%s' % (self.__params.Url, path)
            with async_timeout.timeout(self.__timeout):
                self.__logger.debug('Calling SearchByOwner for %s ...' % cik)
                response = await self.__connection.get(url=url)
                self.__logger.debug('SearchByOwner Response for %s Code: %s' % (cik, response.status))
                if response.status != 200:
                    self.__logger.error('Status Error GetTransactionsByOwner for %s. Response: %s' % (cik, response))
                    return cik, None, [response.status]
                statuses.append(response.status)
                payload = await response.text()
                self.__logger.debug(payload)
                soup = bs4.BeautifulSoup(payload, "html.parser")

                rows = [tr for table in soup.find_all('table')
                        if 'id' in table.attrs if table.attrs['id'] == 'transaction-report'
                        for tr in table.children if tr != '\n']

                if len(rows) <= 1:
                    self.__logger.info('No insider for %s' % cik)
                    return cik, transactions, statuses

                owners = LookupOwners()
                for row in rows[1:]:
                    tds = list(filter(lambda x: x != '\n', row.children))
                    # A/D,DATE,ISSUER,FORM,TYPE,DIRECT/INDIRECT,NUMBER,TOTAL NUMBER,LINE NUMBER,
                    # ISSUER CIK,SECURITY NAME
                    ad = GetText(tds[0])
                    date = GetText(tds[1])
                    if date == '-' or date.startswith(self.__params.StartYear):
                        return cik, transactions, statuses
                    issuer = GetText(tds[3])
                    form = GetText(tds[4])
                    typ = GetText(tds[5])
                    di = GetText(tds[6])
                    num = GetText(tds[7])
                    total = GetText(tds[8])
                    line = GetText(tds[9])
                    i_cik = GetText(tds[10])
                    name = GetText(tds[11])
                    o_type = owners[i_cik] if i_cik in owners else issuer
                    transactions.append((ad, date, issuer, form, typ, di, num.replace('\n', ''), total, line, i_cik,
                                         name.replace(',', ''), o_type.replace(',', '')))

                links = (tag.attrs['onclick'] for tag in soup.find_all('input')
                         if 'type' in tag.attrs if 'button' in tag.attrs['type']
                         and 'Next' in tag.attrs['value'])
                for link in links:
                    self.__logger.debug(link)
                    parts = link.split('?')
                    lnk = parts[1].replace("\\", '').replace("'", '')
                    c, more, moreStatuses = await self.GetTransactionsByOwner(cik, lnk)
                    if more is not None:
                        transactions.extend(more)
                    statuses.extend(moreStatuses)
                return cik, transactions, statuses
        except Exception as e:
            self.__logger.error('Error GetTransactionsByOwner for %s. Response: %s' % (cik, response))
            self.__logger.error(e)
            return cik, None, [500]

    @Connection.ioreliablehttp
    async def GetTransactionsByCompany(self, cik, path=None):
        # https://www.sec.gov/cgi-bin/own-disp
        def LookupOwners():
            lines = [tr for table in soup.find_all('table')
                     for tr in table.children if isinstance(tr, bs4.Tag)
                     and 'Type of Owner' in tr.parent.text and len(tr.contents) == 8]

            lookup = {}
            for i in lines:
                owner_cik = str(i.contents[2].text)
                owner_type = str(i.contents[6].text)
                lookup[owner_cik] = owner_type
            return lookup

        def GetText(tag):
            nxt = tag.next
            while type(nxt) is not bs4.element.NavigableString:
                nxt = nxt.next
            return nxt

        try:
            transactions = []
            statuses = []
            response = None
            path = path if path is not None else \
                'action=getissuer&CIK=%s' % cik
            url = '%s/cgi-bin/own-disp?%s' % (self.__params.Url, path)
            with async_timeout.timeout(self.__timeout):
                self.__logger.debug('Calling SearchByCIK for %s ...' % cik)
                response = await self.__connection.get(url=url)
                self.__logger.debug('SearchByCIK Response for %s Code: %s' % (cik, response.status))
                if response.status != 200:
                    self.__logger.error('Status Error GetTransactionsByCompany for %s. Response: %s' % (cik, response))
                    return cik, None, [response.status]
                statuses.append(response.status)
                payload = await response.text()
                self.__logger.debug(payload)
                soup = bs4.BeautifulSoup(payload, "html.parser")

                rows = [tr for table in soup.find_all('table')
                        if 'id' in table.attrs if table.attrs['id'] == 'transaction-report'
                        for tr in table.children if tr != '\n']

                if len(rows) <= 1:
                    self.__logger.info('No insider for %s' % cik)
                    return cik, transactions, statuses

                owners = LookupOwners()
                for row in rows[1:]:
                    tds = list(filter(lambda x: x != '\n', row.children))
                    # A/D,DATE,OWNER,FORM,TYPE,DIRECT/INDIRECT,NUMBER,TOTAL NUMBER,LINE NUMBER,
                    # OWNER CIK,SECURITY NAME,OWNER TYPE
                    ad = GetText(tds[0])
                    date = GetText(tds[1])
                    if date == '-' or date.startswith(self.__params.StartYear):
                        return cik, transactions, statuses
                    owner = GetText(tds[3])
                    form = GetText(tds[4])
                    typ = GetText(tds[5])
                    di = GetText(tds[6])
                    num = GetText(tds[7])
                    total = GetText(tds[8])
                    line = GetText(tds[9])
                    o_cik = GetText(tds[10])
                    name = GetText(tds[11])
                    o_type = owners[o_cik] if o_cik in owners else owner
                    transactions.append((ad, date, owner, form, typ, di, num.replace('\n', ''), total, line, o_cik,
                                         name.replace(',', ''), o_type.replace(',', '')))

                links = (tag.attrs['onclick'] for tag in soup.find_all('input')
                         if 'type' in tag.attrs if 'button' in tag.attrs['type']
                         and 'Next' in tag.attrs['value'])
                for link in links:
                    self.__logger.debug(link)
                    parts = link.split('?')
                    lnk = parts[1].replace("\\", '').replace("'", '')
                    c, more, moreStatuses = await self.GetTransactionsByCompany(cik, lnk)
                    if more is not None:
                        transactions.extend(more)
                    statuses.extend(moreStatuses)
                return cik, transactions, statuses
        except Exception as e:
            self.__logger.error('Error GetTransactionsByCompany for %s. Response: %s' % (cik, response))
            self.__logger.error(e)
            return cik, None, [500]

    @Connection.ioreliable
    async def GetDailyIndex(self, today):
        try:
            d = today.strftime('%Y%m%d')
            m = today.month
            y = today.year
            if m <= 3:
                quarter = 'QTR1'
            elif 3 < m <= 6:
                quarter = 'QTR2'
            elif 6 < m <= 9:
                quarter = 'QTR3'
            else:
                quarter = 'QTR4'
            url = '%s/Archives/edgar/daily-index/%s/%s/master.%s.idx' % (self.__params.Url, y, quarter, d)
            with async_timeout.timeout(self.__timeout):
                self.__logger.debug('Calling GetDailyIndex for %s ...' % d)
                response = await self.__connection.get(url=url)
                self.__logger.debug('GetDailyIndex Response for %s Code: %s' % (d, response.status))
                payload = await response.text()
                self.__logger.info('url: %s. payload: %s' % (url, payload))
                return payload
        except Exception as e:
            self.__logger.info('Error GetDailyIndex for %s' % d)
            self.__logger.error(e)
            return None

    @Connection.ioreliable
    async def GetCompaniesByState(self, state, path=None):
        def GetText(tag):
            nxt = tag.next
            while type(nxt) is not bs4.element.NavigableString:
                nxt = nxt.next
            return nxt

        try:
            companies = []
            path = path if path is not None else \
                'company=&match=&filenum=&State=%s&Country=&SIC=&myowner=include&action=getcompany&count=%s' % \
                (state, self.__params.PageSize)
            url = '%s/cgi-bin/browse-edgar?%s' % (self.__params.Url, path)
            with async_timeout.timeout(self.__timeout):
                self.__logger.debug('Calling SearchByState for %s ...' % state)
                response = await self.__connection.get(url=url)
                self.__logger.debug('SearchByState Response for %s Code: %s' % (state, response.status))
                payload = await response.text()
                soup = bs4.BeautifulSoup(payload, "html.parser")

                rows = [tr for table in soup.find_all('table')
                        if 'summary' in table.attrs if 'Results' in table.attrs['summary']
                        for tr in table.children if tr != '\n']
                for row in rows:
                    tds = list(filter(lambda x: x != '\n', row.children))
                    cik = GetText(tds[0])
                    name = GetText(tds[1])
                    if cik != 'CIK':
                        companies.append((cik, name, state))

                links = (tag.attrs['onclick'] for tag in soup.find_all('input')
                         if 'type' in tag.attrs if 'button' in tag.attrs['type']
                         and 'Next %s' % self.__params.PageSize in tag.attrs['value'])
                for link in links:
                    self.__logger.debug(link)
                    parts = link.split('?')
                    more = await self.GetCompaniesByState(state, parts[1])
                    companies.extend(more)
                return companies
        except Exception as e:
            self.__logger.info('Error GetCompaniesByState for %s' % state)
            self.__logger.error(e)
            return None

    async def __aenter__(self):

        connector = aiohttp.TCPConnector(verify_ssl=False, family=socket.AF_INET, force_close=True,
                                         limit=None, enable_cleanup_closed=True, loop=self.__loop)
        self.__session = aiohttp.ClientSession(loop=self.__loop, connector=connector)
        self.__connection = await self.__session.__aenter__()
        self.__logger.info('Session created')
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.__connection.close()
        await self.__session.__aexit__(*args, **kwargs)
        self.__logger.info('Session destroyed')


class Scheduler:
    def __init__(self, notify, params, logger, loop=None):
        self.Timeout = params.Timeout
        self.__logger = logger
        self.__params = params
        self.__notify = notify
        self.__loop = loop if loop is not None else asyncio.get_event_loop()

    def InvestmentFound(self, items, arn, date):
        try:
            self.__db.UpdateResults(date, items)
            message = {'DATE': date.strftime('%Y-%m-%d'), 'FOUND': [cik for cik, *other in items]}
            response = self.sns.publish(
                TargetArn=arn,
                Message=json.dumps({'default': json.dumps(message)}),
                MessageStructure='json',
                Subject='Blue Horseshoe loves Anacott Steel'
            )
            self.__logger.info(response)
        except Exception as e:
            self.__logger.error(e)

    def Notify(self, items, arn, today, requestId, chunk):
        try:
            message = {'Date': int(today.strftime('%Y%m%d')), 'CIK': items, 'RequestId': requestId, 'ChunkId': chunk}

            queue = self.sqs.get_queue_by_name(QueueName=arn)
            response = queue.send_message(MessageBody=json.dumps(message))
            '''
            response = self.sns.publish(
                TargetArn=arn,
                Message=json.dumps({'default': json.dumps(message)}),
                MessageStructure='json',
                Subject='FOUND'
            )
            '''
            self.__logger.info(response)
        except Exception as e:
            self.__logger.error(e)

    def SendError(self, message, arn):
        try:
            response = self.sns.publish(
                TargetArn=arn,
                Message=message,
                MessageStructure='text',
                Subject='INSIDERS ERROR'
            )
            self.__logger.info(response)
        except Exception as e:
            self.__logger.error(e)

    def AnalyseThat(self, date, arn, count):
        issuers = self.__db.GetAnalytics('ISSUERS', date, Period.MONTH)
        if len(issuers) == 0:
            self.SendError('No ISSUERS to analyse on %s' % date.strftime('%Y-%m-%d'), arn)
            return
        all_processed_cik = list(set([cik for found in issuers for cik in found['Message']['Processed']]))
        self.__logger.info(all_processed_cik)
        self.__db.ReadFireHose(FileType.ISSUER, all_processed_cik, date)
        investments = []

        for cik in all_processed_cik:
            df = self.__db.GetTimeSeries(cik, FileType.ISSUER)

            if df is None:
                self.__logger.error('Error: %s' % cik)
                self.SendError('Error reading %s from S3 on %s' % (cik, date.strftime('%Y-%m-%d')), arn)
                continue

            cik, pLM, pBLM, pRatio, mLM, mBLM, mRatio = self.__engine.ClusterBuying(df, date, count, cik)
            if pLM > count:
                self.__logger.info('investment found in %s' % cik)
                investments.append((cik, pLM, pBLM, pRatio, mLM, mBLM, mRatio))

        self.__logger.info('Processing %s CIK issuers' % len(all_processed_cik))
        if len(investments) > 0:
            self.InvestmentFound(investments, self.__notify, date)

    def UpdateProcessed(self, today, requestId, chunk_id):
        savings = self.__db.GetAnalytics('SAVING', today, Period.DAY)
        for saving in savings:
            if saving['RequestId'] == requestId and saving['Chunks'] == chunk_id:
                self.__db.UpdateAnalytics('SAVING', saving['TransactionTime'], True)
                self.__logger.info('Updated SAVING: %s, chunkId: %s' % (requestId, chunk_id))
            if saving['RequestId'] == requestId and '.' in str(chunk_id) and str(chunk_id).startswith(str(saving['Chunks'])):
                self.__db.UpdateAnalytics('SAVING', saving['TransactionTime'], True)
                self.__logger.info('Updated parent SAVING: %s, chunkId: %s' % (requestId, saving['Chunks']))

    def CheckIfProcessed(self, items, today, requestId, chunk_id):
        savings = self.__db.GetAnalytics('SAVING', today, Period.DAY)
        for saving in savings:
            if saving['RequestId'] == requestId and saving['Chunks'] == chunk_id:
                self.__logger.info('Already processed requestId: %s, chunkId: %s' % (requestId, chunk_id))
                return True

        self.__db.SaveAnalytics('SAVING', 'Batch of CIKs to process',
                                {'Received': items}, today, len(items), requestId, chunk_id)
        self.__logger.info('Start processing requestId: %s, chunkId: %s' % (requestId, chunk_id))
        return False

    def ValidateResults(self, date, arn, fix, found_arn, delay, buffer):
        founds = self.__db.GetAnalytics('FOUND', date, Period.DAY)
        savings = self.__db.GetAnalytics('SAVING', date, Period.DAY)
        owners = self.__db.GetAnalytics('OWNERS', date, Period.DAY)
        issuers = self.__db.GetAnalytics('ISSUERS', date, Period.DAY)
        if len(founds) == 0 or len([f for f in founds if f['Count'] == 0]):
            message = 'No FOUND events on %s' % date.strftime('%Y-%m-%d')
            self.SendError(message, arn)
            self.__logger.warn(message)
            return

        for item in owners:
            errors = [code for code in item['Message']['Codes'] if code != 200]
            if len(errors) > 0:
                message = 'OWNERS events have %s errors on %s for %s %s' \
                          % (errors, date.strftime('%Y-%m-%d'), item['RequestId'], item['Chunks'])
                self.SendError(message, arn)
                self.__logger.warn(message)

        for item in issuers:
            errors = [code for code in item['Message']['Codes'] if code != 200]
            if len(errors) > 0:
                message = 'ISSUERS events have %s errors on %s for %s %s' \
                          % (errors, date.strftime('%Y-%m-%d'), item['RequestId'], item['Chunks'])
                self.SendError(message, arn)
                self.__logger.warn(message)

        for saving in savings:
            if 'Processed' not in saving:
                self.__logger.info('resending %s %s on %s' % (saving['RequestId'], saving['Chunks'], date))
                not_processed = saving['Message']['Received']
                if not fix:
                    message = '%s events are still not processed on %s for %s %s' % \
                              (not_processed, date.strftime('%Y-%m-%d'), saving['RequestId'], saving['Chunks'])
                    self.SendError(message, arn)
                    self.__logger.warn(message)
                else:
                    chunks = [not_processed[x:x + buffer] for x in range(0, len(not_processed), buffer)]
                    i = 0
                    for chunk in chunks:
                        i += 1
                        chunk_id = '%s.%s' % (saving['Chunks'], i)
                        chunk = [int(x) for x in chunk]
                        self.Notify(chunk, found_arn, date, saving['RequestId'], chunk_id)
                        time.sleep(delay)
                        self.__logger.warn('Resending %s' % chunk)
            else:
                self.__logger.info('All events processed on %s for %s %s' % (date.strftime('%Y-%m-%d'),
                                                                             saving['RequestId'], saving['Chunks']))

    def Save(self, message, today, action, count, desc, requestId, chunk):
        self.__db.SaveAnalytics(action, desc,
                                message, today, count, requestId, chunk)

    async def SyncDailyIndex(self, today):
        found = {}
        done = await self.__edgarConnection.GetDailyIndex(today)
        for line in done.split('\n'):
            cells = line.split('|')
            if len(cells) == 5 and (cells[2] == '4' or cells[2] == '4/A'):
                found[cells[0]] = cells[0]
        return [int(x) for x in found]

    async def SyncTransactions(self, items, file_type):
        self.__logger.info('Loaded %s: %s' % (file_type, len(items)))

        successful = []
        all_stats = []
        if file_type == FileType.ISSUER:
            futures = [self.__edgarConnection.GetTransactionsByCompany(str(cik)) for cik in items]
        if file_type == FileType.OWNER:
            futures = [self.__edgarConnection.GetTransactionsByOwner(str(cik)) for cik in items]
        done, pending = await asyncio.wait(futures, timeout=self.Timeout)

        for pending_task in pending:
            self.__logger.error('Cancelling the task: {}'.format(pending_task))
            pending_task.cancel()

        # A/D,DATE,OWNER,FORM,TYPE,DIRECT/INDIRECT,NUMBER,TOTAL NUMBER,LINE NUMBER, OWNER CIK,SECURITY NAME,OWNER TYPE
        for fut in done:
            try:
                cik, payload, status = fut.result()
                all_stats.extend(status)
                if payload is not None and len(payload) > 1 \
                        and len([date for ad, date, owner_issuer, form, tt, *o in payload if tt == 'P-Purchase']) > 1:
                    # self.__logger.info(payload)
                    count = 0
                    all_trans = []
                    for tran in payload:
                        count += 1
                        ad, date, owner_issuer, form, tran_type, di, num, total, line, o_cik, sec_name, o_type = tran
                        all_trans.append((str(ad), str(date), str(owner_issuer), str(form), str(tran_type), str(di),
                                          str(num), str(total), str(line), str(o_cik), str(sec_name), str(o_type)))

                    if file_type == FileType.ISSUER:
                        self.__db.UpdateTransactions(cik, all_trans)
                    if file_type == FileType.OWNER:
                        self.__db.UpdateOwnersTransactions(cik, all_trans)
                    successful.append(cik)
                    self.__logger.info('Updated %s transactions for %s. CIK %s' % (len(all_trans), file_type, cik))
            except Exception as e:
                self.__logger.error('Exception in SyncTransactions: {}'.format(e))
        return successful, all_stats

    async def SyncCompanies(self):
        states = self.__insiderSession.GetStates()

        self.__logger.info('Loaded states: %s' % states)

        futures = [self.__edgarConnection.GetCompaniesByState(code) for code, name, *country in states]
        done, _ = await asyncio.wait(futures, timeout=self.Timeout)

        all_companies = []
        for fut in done:
            payload = fut.result()
            if payload is not None and len(payload) > 1:
                code, name, state = payload[0]
                self.__logger.info('%s Companies in %s' % (len(payload), state))
                count = 0
                for company in payload:
                    count += 1
                    code, name, state = company
                    all_companies.append((str(code), str(state), str(name)))
        self.__db.UpdateCompanies(all_companies)
        self.__logger.info('Updated %s companies' % len(all_companies))

    async def __aenter__(self):
        self.__engine = DecisionEngine(self.__notify, self.__logger)
        self.__client = EdgarClient(self.__params, self.__logger, self.__loop)
        self.__edgarConnection = await self.__client.__aenter__()
        self.__db = StoreManager(self.__logger, self.__notify, self.Timeout)
        self.__insiderSession = self.__db.__enter__()
        self.sns = boto3.client('sns')
        self.sqs = boto3.resource('sqs')
        self.__logger.info('Scheduler created')
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.__client.__aexit__(*args, **kwargs)
        self.__db.__exit__(*args, **kwargs)
        self.__logger.info('Scheduler destroyed')
