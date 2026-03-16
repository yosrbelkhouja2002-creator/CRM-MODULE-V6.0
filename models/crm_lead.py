# -*- coding: utf-8 -*-
from odoo import models, fields, api # type: ignore
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT # type: ignore
import datetime

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ✅ Lien vers la veille commerciale qui a généré ce lead
    piste_source_id = fields.Many2one(
        'piste.source',
        string="Veille commerciale",
        index=True,
        ondelete='set null',
    )

    @api.model
    def create(self, vals):
        # Si name n'est pas fourni (typique du quick-create ou création minimale)
        if 'name' not in vals or not vals.get('name'):
            now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')
            if vals.get('type') == 'opportunity':
                vals['name'] = f"Nouvelle opportunité - {now}"
            else:
                vals['name'] = f"Nouveau lead - {now}"
        return super(CrmLead, self).create(vals)