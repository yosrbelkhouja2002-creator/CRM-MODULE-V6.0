# -*- coding: utf-8 -*-
from odoo import models, fields

class PisteOffer(models.Model):
    _name = 'piste.offer'
    _description = 'Projet commercial trouvé'
    _rec_name = 'name'
    _order = 'scraped_date desc'
    
    # ===== CHAMPS DE BASE =====
    name = fields.Char(string='Titre du projet')  
    # RELATION AVEC LA SOURCE
    source_id = fields.Many2one(
        'piste.source',
        string='Source',
        ondelete='cascade'
    )  # ← Plus obligatoire
    
    # INFORMATIONS DU PROJET
    url = fields.Char(string='URL')
    description = fields.Html(string='Description')
    website = fields.Char(string='Plateforme')
    budget = fields.Char(string='Budget')
    
    # ===== CHAMPS CLIENT/CONTACT =====
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        help='Entreprise cliente'
    )
    
    person_partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        help='Personne de contact'
    )
    
    Mode_de_livraison = fields.Selection([
        ('regie', 'Régie'),
        ('forfait', 'Forfait'),
        ('mixte', 'Mixte'),
    ], string='Mode de livraison')
    
    business_unit_id = fields.Many2one(
        'business.unit',
        string='Business unit',
        help='Unité commerciale responsable'
    )
    
    # STATUT
    status = fields.Selection([
        ('new', 'Nouveau'),
        ('read', 'Lu'),
        ('qualified', 'Qualifié'),
        ('ignored', 'Ignoré'),
        ('converted', 'Converti en Lead')
    ], string='Statut', default='new')  # ← Plus obligatoire
    
    # DATES
    publication_date = fields.Date(string='Date de publication')
    scraped_date = fields.Datetime(
        string='Date de détection',
        default=fields.Datetime.now
    )  # ← Plus obligatoire
    
    # NOTES
    notes = fields.Text(string='Notes commerciales')
    
    # LIEN VERS LEAD CRM
    lead_id = fields.Many2one('crm.lead', string='Lead CRM')