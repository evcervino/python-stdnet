import logging

from inspect import isclass

from stdnet import getdb, AsyncObject
from stdnet.utils.encoders import Json
from stdnet.utils import is_string


logger = logging.getLogger('stdnet.pubsub')


class PubSubBase(object):
    pickler = Json
    
    def __init__(self, server=None, pickler=None):
        pickler = pickler or self.pickler
        if isclass(pickler):
            pickler = pickler()
        self.pickler = pickler
        self.server = getdb(server)
        
    
class Publisher(PubSubBase):
    '''Class which publish messages to message queues.'''        
    def publish(self, channel, data):
        data = self.pickler.dumps(data)
        return self.server.publish(channel, data)
    
    
class Subscriber(PubSubBase):
    '''A subscriber to channels'''
    def __init__(self, server=None, pickler=None):
        super(Subscriber, self).__init__(server, pickler)
        self.channels = {}
        self.patterns = {}
        self._subscriber = self.server.subscriber(
                                message_callback=self.message_callback)
        
    def disconnect(self):
        self._subscriber.disconnect()
    
    def subscription_count(self):
        return self._subscriber.subscription_count()
    
    def subscribe(self, *channels):
        return self._subscriber.subscribe(self.channel_list(channels))
     
    def unsubscribe(self, *channels):
        return self._subscriber.unsubscribe(self.channel_list(channels))
    
    def psubscribe(self, *channels):
        return self._subscriber.psubscribe(self.channel_list(channels))
    
    def punsubscribe(self, *channels):
        return self._subscriber.punsubscribe(self.channel_list(channels))

    def message_callback(self, command, channel, message=None):
        if command == 'subscribe':
            self.channels[channel] = []
        elif command == 'unsubscribe':
            self.channels.pop(channel, None)
        elif channel in self.channels:
            self.channels[channel].append(self.pickler.loads(message))
        else:
            logger.warn('Got message for unsubscribed channel "%s"' % channel)
    
    def get_all(self, channel=None):
        if channel is None:
            channels = {}
            for channel in self.channels:
                data = self.channels[channel]
                if data:
                    channels[channel] = data
                    self.channels[channel] = []
            return channels
        elif channel in self.channels:
            data = self.channels[channel]
            self.channels[channel] = []
            return data
        
    def pool(self):
        '''Pull data from subscribed channels.
        
:param timeout: Pool timeout in seconds'''
        return self._subscriber.pool()
        
    def channel_list(self, channels):
        ch = []
        for channel in channels:
            if not isinstance(channel, (list, tuple)):
                ch.append(channel)
            else:
                ch.extend(channel)
        return ch
