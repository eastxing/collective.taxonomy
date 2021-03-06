import logging
import generated

from persistent import Persistent

from plone.autoform.interfaces import WRITE_PERMISSIONS_KEY, WIDGETS_KEY
from plone.behavior.interfaces import IBehavior
from plone.directives import form
from plone.dexterity.interfaces import IDexterityContent
from plone.indexer.interfaces import IIndexer
from plone.registry.interfaces import IRegistry
from plone.registry import Record, field
from plone.supermodel.interfaces import FIELDSETS_KEY
from plone.supermodel.model import Fieldset
from plone.supermodel.model import SchemaClass

from Products.CMFCore.utils import getToolByName
from Products.PluginIndexes.KeywordIndex.KeywordIndex import KeywordIndex
from Products.ZCatalog.Catalog import CatalogError
from Products.ZCatalog.interfaces import IZCatalog

from zope import schema
from zope.component.hooks import getSite
from zope.interface import implements, alsoProvides, Invalid
from zope.component import getUtility, provideAdapter

from z3c.form import validator

from .i18n import MessageFactory as _
from .indexer import TaxonomyIndexer

logger = logging.getLogger("collective.taxonomy")


class TaxonomyBehavior(Persistent):
    implements(IBehavior)

    def __init__(self, name, title, description, field_title,
                 field_description, is_required=False,
                 write_permission=''):
        self.name = name
        self.title = _(title)
        self.description = _(description)
        self.factory = None
        self.field_title = field_title
        self.field_description = field_description
        self.is_required = is_required
        self.write_permission = write_permission

    def deactivateSearchable(self):
        registry = getUtility(IRegistry)
        prefix = 'plone.app.querystring.field.' + self.field_name
        for suffix in ('title', 'enabled', 'group',
                       'operations', 'vocabulary', 'sortable', 'description'):
            record_name = prefix + '.' + suffix
            if record_name in registry.records:
                del registry.records[record_name]

    def removeIndex(self):
        context = getSite()
        sm = context.getSiteManager()
        sm.unregisterAdapter(TaxonomyIndexer, (IDexterityContent, IZCatalog),
                             IIndexer, name=self.field_name)

        catalog = getToolByName(context, 'portal_catalog')
        try:
            catalog.delIndex(self.field_name)
        except CatalogError:
            logging.info("Could not delete index " + self.field_name +
                         " something is not right..")

    def activateSearchable(self):
        registry = getUtility(IRegistry)
        prefix = 'plone.app.querystring.field.' + self.field_name

        def add(name, value):
            registry.records[prefix + '.' + name] = value

        add('title', Record(field.TextLine(), unicode(self.field_title)))
        add('enabled', Record(field.Bool(), True))
        add('group', Record(field.TextLine(), unicode('Taxonomy')))
        add('operations', Record(field.List(),
            ['plone.app.querystring.operation.selection.is']))
        add('vocabulary', Record(field.TextLine(), unicode(self.name)))
        add('sortable', Record(field.Bool(), False))
        add('description', Record(field.Text(), unicode('')))

    def addIndex(self):
        context = getSite()
        sm = context.getSiteManager()
        sm.registerAdapter(
            TaxonomyIndexer(self.field_name, self.name),
            (IDexterityContent, IZCatalog),
            IIndexer, name=self.field_name)

        catalog = getToolByName(context, 'portal_catalog')
        idx_object = KeywordIndex(str(self.field_name))
        try:
            catalog.addIndex(self.field_name, idx_object)
        except CatalogError:
            logging.info("Index " + self.field_name +
                         " already exists, we hope it is proper configured")

    def unregisterInterface(self):
        if hasattr(generated, self.short_name):
            delattr(generated, self.short_name)

    @property
    def short_name(self):
        return str(self.name.split('.')[-1])

    @property
    def field_name(self):
        return 'taxonomy_' + self.short_name

    @property
    def vocabulary_name(self):
        return 'collective.taxonomy.' + self.short_name

    @property
    def interface(self):
        return getattr(generated, self.short_name)

    @property
    def marker(self):
        return getattr(generated, self.short_name)

    def generateInterface(self):
        logger.debug('generating interface for %s' % self.short_name)

        if self.is_required:
            select_field = schema.List(
                title=_(unicode(self.field_title)),
                description=_(unicode(self.field_description)),
                required=True,
                constraint=lambda value: bool(value),

                value_type=schema.Choice(
                    vocabulary=self.vocabulary_name,
                    required=True
                )
            )
        else:
            select_field = schema.List(
                title=_(unicode(self.field_title)),
                description=_(unicode(self.field_description)),
                required=False,
                value_type=schema.Choice(
                    vocabulary=self.vocabulary_name,
                    required=False
                )
            )

        schemaclass = SchemaClass(
            self.short_name, (form.Schema, ),
            __module__='collective.taxonomy.generated',
            attrs={str(self.field_name):
                   select_field }
        )

        if self.write_permission:
            schemaclass.setTaggedValue(
                WRITE_PERMISSIONS_KEY,
                {self.field_name:
                 self.write_permission}
            )

        schemaclass.setTaggedValue(
            FIELDSETS_KEY,
            [Fieldset('categorization',
                      fields=[self.field_name])]
        )

        schemaclass.setTaggedValue(
            WIDGETS_KEY,
            {self.field_name:
             'collective.taxonomy.widget.TaxonomySelectFieldWidget'}
        )

        alsoProvides(schemaclass, form.IFormFieldProvider)
        return schemaclass
