import copy
import json

from stdnet import async
from stdnet.utils import zip, JSPLITTER, EMPTYJSON, iteritems
from stdnet.utils.exceptions import *

from .base import StdNetType, Model
from .session import Session, Manager
from . import signals


__all__ = ['StdModel', 'model_to_dict']


StdNetBase = StdNetType('StdNetBase', (Model,), {})


class StdModel(StdNetBase):
    '''A :class:`Model` which contains data in :class:`Field`.

.. attribute:: _meta

    A class attribute which is an instance of :class:`Metaclass`, it
    containes all the information needed by a :class:`stdnet.backendServer`.
    
.. attribute:: objects

    A class attribute available when this model is
    :ref:`registered with a backend server <register-model>`. it is
    a :class:`Manager` for obtaining :class:`Session` and :class:`Query`.
    
.. attribute:: searchengine

    A class attribute available when this model is registered and installed
    with a :class:`SearchEngine` for full text search. Check the
    :meth:`SearchEngine.register` documentation for more information. 

.. attribute:: id

    The instance primary key.

.. attribute:: uuid

    Universally unique identifier for an instance.

.. attribute:: session

    the :class:`Session` instance which loaded the instance (available
    when the instance is loaded from the data server).
'''
    _model_type = 'object'
    searchengine = None
    is_base_class = True
    _loadedfields = None

    def __init__(self, **kwargs):
        kwargs.pop(self._meta.pkname(), None)
        for field in self._meta.scalarfields:
            self.set_field_value(field, kwargs.pop(field.name, None))
        if kwargs:
            keys = ', '.join(kwargs)
            if len(kwargs) > 1:
                keys += ' are'
            else:
                keys += ' is an'
            raise ValueError("%s invalid keyword for %s." % (keys, self._meta))

    @property
    def has_all_data(self):
        '''``True`` if this :class:`StdModel` instance has all back-end data
loaded. This applies to persistent instances only. This property is used when
committing changes. If all data is available, the commit will replace the
previous object data entirely, otherwise it will only update it.'''
        return self.get_state().persistent and self._loadedfields is None
    
    def loadedfields(self):
        '''Generator of fields loaded from database'''
        if self._loadedfields is None:
            for field in self._meta.scalarfields:
                yield field
        else:
            fields = self._meta.dfields
            processed = set()
            for name in self._loadedfields:
                if name in processed:
                    continue
                if name in fields:
                    processed.add(name)
                    yield fields[name]
                else:
                    name = name.split(JSPLITTER)[0]
                    if name in fields and name not in processed:
                        field = fields[name]
                        if field.type == 'json object':
                            processed.add(name)
                            yield field

    def fieldvalue_pairs(self, exclude_cache=False):
        '''Generator of fields,values pairs. Fields correspond to
the ones which have been loaded (usually all of them) or
not loaded but modified.
Check the :ref:`load_only <performance-loadonly>` query function for more
details.

If *exclude_cache* evaluates to ``True``, fields with :attr:`Field.as_cache`
attribute set to ``True`` won't be included.

:rtype: a generator of two-elements tuples'''
        for field in self._meta.scalarfields:
            if exclude_cache and field.as_cache:
                continue
            name = field.attname
            if hasattr(self, name):
                yield field, getattr(self,name)

    def set_field_value(self, field, value):
        value = field.to_python(value)
        setattr(self, field.attname, value)
        return value

    def clear_cache_fields(self):
        '''Set cache fields to ``None``. Check :attr:`Field.as_cache`
for information regarding fields which are considered cache.'''
        for field in self._meta.scalarfields:
            if field.as_cache:
                setattr(self,field.name,None)

    def get_attr_value(self, name):
        '''Retrieve the ``value`` for the attribute ``name``. The ``name``
can be nested following the :ref:`double underscore <tutorial-underscore>`
notation, for example ``group__name``. If the attribute is not available it
raises :class:`AttributeError`.'''
        if name in self._meta.dfields:
            return self._meta.dfields[name].get_value(self)
        elif not name.startswith('__') and JSPLITTER in name:
            bits = name.split(JSPLITTER)
            fname = bits[0]
            if fname in self._meta.dfields:
                return self._meta.dfields[fname].get_value(self, bits[1:])
            else:
                return getattr(self, name)
        else:
            return getattr(self, name)

    def clone(self, **data):
        '''Utility method for cloning the instance as a new object.

:parameter data: additional which override field data.
:rtype: a new instance of this class.
'''
        meta = self._meta
        session = self.session
        pkname = meta.pkname()
        pkvalue = data.pop(pkname, None)
        fields = self.todict(exclude_cache=True)
        fields.update(data)
        fields.pop('__dbdata__', None)
        obj = self._meta.make_object((pkvalue, None, fields))
        obj.session = session
        return obj

    def is_valid(self):
        '''Kick off the validation algorithm by checking all
:attr:`StdModel.loadedfields` against their respective validation algorithm.

:rtype: Boolean indicating if the model validates.'''
        return self._meta.is_valid(self)

    def obtain_session(self):
        if self.session is not None:
            return self.session.session()
        else:
            return self.__class__.objects.session()

    def todict(self, exclude_cache=False):
        '''Return a dictionary of serialised scalar field for pickling.
If the *exclude_cache* flag is ``True``, fields with :attr:`Field.as_cache`
attribute set to ``True`` will be excluded.'''
        odict = {}
        for field,value in self.fieldvalue_pairs(exclude_cache=exclude_cache):
            value = field.serialize(value)
            if value:
                odict[field.name] = value
        if 'id' in self._dbdata:
            odict['__dbdata__'] = {'id': self._dbdata['id']}
        return odict

    def _to_json(self, exclude_cache):
        pk = self.pkvalue()
        if pk:
            yield self._meta.pkname(),pk
            for field,value in self.fieldvalue_pairs(exclude_cache=\
                                                     exclude_cache):
                value = field.json_serialize(value)
                if value not in EMPTYJSON:
                    yield field.name,value

    def tojson(self, exclude_cache=True):
        '''return a JSON serializable dictionary representation.'''
        return dict(self._to_json(exclude_cache))

    def load_fields(self, *fields):
        '''Load extra fields to this :class:`StdModel`.'''
        if self._loadedfields is not None:
            meta = self._meta
            kwargs = {meta.pkname(): self.pkvalue()}
            obj = self.__class__.objects.query().load_only(fields).get(**kwargs)
            for name in fields:
                field = meta.dfields.get(name)
                if field is not None:
                    setattr(self,field.attname,getattr(obj,field.attname,None))

    def post_commit(self, callable, **params):
        signals.post_commit.add_callback(lambda *args, **kwargs:\
                                          callable(self, kwargs, **params),
                                          sender=self._meta.model)
        return self
    
    def get_state_action(self):
        return 'override' if self._loadedfields is None else 'update'
                
    def load_related_model(self, name, load_only=None, dont_load=None):
        '''Load a the :class:`ForeignKey` field ``name`` if this is part of the
fields of this model and if the related object is not already loaded.
It is used by the lazy loading mechanism of :ref:`one-to-many <one-to-many>`
relationships.

:parameter name: the :attr:`Field.name` of the :class:`ForeignKey` to load.
:parameter load_only: Optional parameters which specify the fields to load.
:parameter dont_load: Optional parameters which specify the fields not to load.
:return: the related :class:`StdModel` instance.
'''
        field = self._meta.dfields.get(name)
        if not field:
            raise ValueError('Field "%s" not available' % name)
        elif not field.type == 'related object':
            raise ValueError('Field "%s" not a foreign key' % name)
        return self._load_related_model(field, load_only, dont_load)
        
    @async()
    def _load_related_model(self, field, load_only=None, dont_load=None):
        cache_name = field.get_cache_name()
        if hasattr(self, cache_name):
            yield getattr(self, cache_name)
        else:
            val = getattr(self, field.attname)
            if val is None:
                rel_obj = None
            else:
                pkname = field.relmodel._meta.pkname()
                qs = self.session.query(field.relmodel)
                if load_only:
                    qs = qs.load_only(*load_only)
                if dont_load:
                    qs = qs.dont_load(*dont_load) 
                all = yield qs.filter(**{pkname: val}).all()
                if all:
                    rel_obj = qs._get(all)
                else:
                    if field.required:
                        raise self.DoesNotExist
                    else:
                        rel_obj = None
                    setattr(self, field.attname, None)
            setattr(self, cache_name, rel_obj)
            yield rel_obj
    
    @classmethod
    def get_field(cls, name):
        '''Returns the :class:`Field` instance at ``name`` if available,
otherwise it returns ``None``.'''
        return cls._meta.dfields.get(name)
    
    @classmethod
    def from_base64_data(cls, **kwargs):
        o = cls()
        meta = cls._meta
        pkname = meta.pkname()
        for name,value in iteritems(kwargs):
            if name == pkname:
                field = meta.pk
            elif name in meta.dfields:
                field = meta.dfields[name]
            else:
                continue
            value = field.to_python(value)
            setattr(o,field.attname,value)
        return o
    
    @classmethod
    def pk(cls):
        '''Return the primary key :class:`Field` for this model. This is a
proxy for the :attr:`Metaclass.pk` attribute::
    
    MyModel.pk() == MyModel._meta.pk
    
'''
        return cls._meta.pk
    
    # PICKLING SUPPORT

    def __getstate__(self):
        return (self.id, self._loadedfields, self.todict())

    def __setstate__(self, state):
        self._meta.make_object(state)



def model_to_dict(instance, fields=None, exclude=None):
    if isinstance(instance,StdModel):
        return instance.todict()
    else:
        d = {}
        for field in instance._meta.fields:
            default = field.get_default()
            if default:
                d[field.name] = default
        return d

