# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# PWNDD Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# Contract No: HR00112590083
# Contractor Name: RTX BBN Technologies Inc.
# Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
#
# The U.S. Government's rights to use, modify, reproduce, release, perform,
# display, or disclose these technical data and software are defined in the
# Article VII: Data Rights clause of the OTA.
#
# This document does not contain technology or technical data controlled under
# either the U.S. International Traffic in Arms Regulations or the U.S. Export
# Administration Regulations.
#
# DISTRIBUTION STATEMENT A: Approved for public release; distribution is
# unlimited.
#
# Notice: Markings. Any reproduction of this computer software, computer
# software documentation, or portions thereof must also reproduce the markings
# contained herein.
#
# MAUDE_HCS: end

import logging
logger = logging.getLogger(__name__)

from maude_hcs.parsers.graph import Topology, Node, Link

class ParameterizedLink:
  '''
  The class for defining parameterized links.
  This is essentially a wrapper around Topology for compiling topo to maude
  '''
  def __init__(self, link:Link) -> None:
    if not link:
      # Default link, when nothing is specified.
      self.delayType  = "Constant"
      self.delayMean  = 0.
      self.delayStd   = 0.
      self.delayConst = 0.002
      self.noiseMin   = 0.
      self.noiseMax   = 0.00001

      self.canDrop    = False
      self.dropP      = 0.
      return
    
    self.link = link
    self.delayStd   = link.jitter * 0.667
    self.delayType  = "Constant" if self.delayStd == 0. else "Normal"
    # T&E V1 used RTT times, this is compatible with V2.
    self.delayMean  = 0. if self.delayStd == 0. else link.latency
    self.delayConst = link.latency if self.delayStd == 0. else 0.
    self.noiseMin   = 0.
    self.noiseMax   = 0.00001 if self.delayStd == 0. else 0.

    # Drop Probability (value must be between 0 and 1.)
    self.dropP      = link.loss / 100.
    self.canDrop    = self.dropP > 0.


  def to_string(self) -> str:
    """
    Create a printable string for this object.

    Return the printable string of the object.
    """
    s  = f"Chars: Type {self.delayType}, "
    s += f"Delay: {self.delayConst}, "
    s += f"NoiseMin: {self.noiseMin}, "
    s += f"NoiseMax: {self.noiseMax}, "
    s += f"Mean: {self.delayMean}, "
    s += f"Std: {self.delayStd}, "
    s += f"canDrop: {self.canDrop}, "
    s += f"prob: {self.dropP}"
    return s


  def _to_maude(self) -> str:
    '''
    Turn object to maude code.
    Return the string of the maude code for this object.
    '''
    maude_str = ""
    terminator= ''
    for parameter, value in self.__dict__.items():
      if parameter == 'link': continue
      if isinstance(value, str):
        maude_str += f'{terminator}  ({parameter}: "{str(value)}")'
      elif isinstance(value, bool):
        maude_str += f"{terminator}  ({parameter}: {str(value).lower()})"
      else:
        formatted_value = f"{value:f}"
        maude_str += f"{terminator}  ({parameter}: {formatted_value.rstrip('0')})"
      terminator = ',\n'
    return maude_str


class ParameterizedTopo:

  def __init__(self, topo: Topology) -> None:
    self.topo = topo
    # Characteristics for each link type.
    self.link_characteristics = dict()
    # Link type counter.
    self.link_type_number = 0
    self._characerize_links()


  def _characerize_links(self) -> None:
    for link in self.topo.links:
      link_type = self.get_link_type(link)
      if not link_type in self.link_characteristics:
        self.link_characteristics[link_type]  = [link]
      else:
        self.link_characteristics[link_type].append(link)

  def get_link_type(self, link: Link) -> str:
    # Look through the link characteristics,
    for link_type, existing_links in self.link_characteristics.items():
      for existing_link in existing_links:
        # If one like this already exists, use that type.
        if existing_link.is_similar_to(link):
            return link_type

    # Did not find a link with the same characteristics; make a new type.
    link_type = f"LinkType-{self.link_type_number}"
    self.link_type_number += 1
    return link_type

  def to_maude_network(self) -> str:
    maude_str   = " --- Link Characteristic definitions\n"
    for link_type, links in self.link_characteristics.items():
      maude_str  += f"op {link_type} : -> AttributeSet .\n"
      maude_str  += f"eq {link_type} = \n"
      link = ParameterizedLink(links[0]) #doesnt matter which one to use
      maude_str  += link._to_maude()
      maude_str  += "\n  .\n\n"

    maude_str += "eq LinkData =\n"
    for link_type, links in self.link_characteristics.items():
      for link in links:
        src_node = self.topo.getNodebyId(link.src_id)
        dst_node = self.topo.getNodebyId(link.dst_id)
        maude_str += f"  aaa({src_node.address},{dst_node.address},{link_type})\n"
    maude_str += ".\n"
    
    return maude_str