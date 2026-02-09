# -*- coding: utf-8 -*-
from odoo import models, fields # type: ignore

class PisteOffer(models.Model):
    _name = 'piste.offer'
    _description = 'Projet commercial trouvé'
    _rec_name = 'name'
    _order = 'scraped_date desc'
    
    # ===== CHAMPS DE BASE =====
    name = fields.Char(string='Titre du projet', required=True)
    
    # RELATION AVEC LA SOURCE
    source_id = fields.Many2one(
        'piste.source',
        string='Source',
        required=True,
        ondelete='cascade'
    )
    
    # INFORMATIONS DU PROJET
    url = fields.Char(string='URL')
    description = fields.Html(string='Description')
    website = fields.Char(string='Plateforme')
    budget = fields.Char(string='Budget')
    
    # STATUT
    status = fields.Selection([
        ('new', 'Nouveau'),
        ('read', 'Lu'),
        ('qualified', 'Qualifié'),
        ('ignored', 'Ignoré'),
        ('converted', 'Converti en Lead')
    ], string='Statut', default='new', required=True)
    
    # DATES
    publication_date = fields.Date(string='Date de publication')
    scraped_date = fields.Datetime(
        string='Date de détection',
        default=fields.Datetime.now,
        required=True
    )
    
    # NOTES
    notes = fields.Text(string='Notes commerciales')
    
    # LIEN VERS LEAD CRM
    lead_id = fields.Many2one('crm.lead', string='Lead CRM')