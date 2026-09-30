"""
Shared synthetic L5X fixture for the editor / validator tests.

Mirrors what Studio 5000 writes: UTF-8 BOM, CRLF line endings, one element per line, CDATA around
every text value. Contains the awkward cases the tools must handle:
  * two programs with a routine of the same name (MainProgram/Main and Other/Main)
  * an empty ladder routine written as <RLLContent/>
  * an ST routine (Line elements in CDATA) and a STRING tag (CDATA data) - what an XML-library
    round trip destroys
  * an Add-On Instruction with Required / optional / Output parameters
  * both the V37 tag style (Class="Standard", OpcUaAccess) and the V35 style
"""


def build_l5x(eol: str = "\r\n", v37: bool = True, tags_self_closing: bool = False,
              main_rungs=None, other_rungs=None, bom: bool = True) -> str:
    main_rungs = main_rungs if main_rungs is not None else [
        ("XIC(Start)OTE(Run);", "start the run bit"),
        ("XIC(Run)TON(Timer1,?,?);", None),
        ("Two_Arg_AOI(AoiInst,Start,Run);", "aoi call"),
    ]
    other_rungs = other_rungs if other_rungs is not None else [("NOP();", None)]

    def rungs_xml(rungs):
        out = []
        for i, (text, comment) in enumerate(rungs):
            out.append(f'<Rung Number="{i}" Type="N">')
            if comment:
                out += ["<Comment>", f"<![CDATA[{comment}]]>", "</Comment>"]
            out += ["<Text>", f"<![CDATA[{text}]]>", "</Text>", "</Rung>"]
        return out

    cls = ' Class="Standard"' if v37 else ""
    opc = ' OpcUaAccess="None"' if v37 else ""

    def tag(name, dtype, l5k, dec, extra=""):
        return [f'<Tag Name="{name}"{cls} TagType="Base" DataType="{dtype}"{extra} Constant="false" ExternalAccess="Read/Write"{opc}>',
                '<Data Format="L5K">', f"<![CDATA[{l5k}]]>", "</Data>", '<Data Format="Decorated">', dec, "</Data>", "</Tag>"]

    tags = []
    if not tags_self_closing:
        tags += tag("Start", "BOOL", "0", '<DataValue DataType="BOOL" Radix="Decimal" Value="0"/>', ' Radix="Decimal"')
        tags += tag("Run", "BOOL", "0", '<DataValue DataType="BOOL" Radix="Decimal" Value="0"/>', ' Radix="Decimal"')
        tags += tag("Timer1", "TIMER", "[0,0,0]",
                    '<Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="0"/></Structure>')
        tags += tag("AoiInst", "Two_Arg_AOI", "[0]", '<Structure DataType="Two_Arg_AOI"></Structure>')
        tags += tag("Message_Text", "STRING", "[5,'Hello$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00']",
                    "<DataValue DataType=\"STRING\" Radix=\"ASCII\" Length=\"5\" Value=\"'Hello'\"/>")

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="35.00" TargetName="Fixture" TargetType="Controller" ContainsContext="false">',
        '<Controller Use="Target" Name="Fixture" ProcessorType="5069-L340ER" MajorRev="35" MinorRev="11">',
        "<DataTypes/>",
        "<Modules>",
        '<Module Name="Local" CatalogNumber="5069-L340ER" Vendor="1" ProductType="14" ProductCode="219" Major="35" Minor="11" ParentModule="Local" ParentModPortId="1" Inhibited="false" MajorFault="true"/>',
        "</Modules>",
        "<AddOnInstructionDefinitions>",
        '<AddOnInstructionDefinition Name="Two_Arg_AOI" Revision="1.0">',
        "<Parameters>",
        '<Parameter Name="EnableIn" TagType="Base" DataType="BOOL" Usage="Input" Radix="Decimal" Required="false" Visible="false"/>',
        '<Parameter Name="EnableOut" TagType="Base" DataType="BOOL" Usage="Output" Radix="Decimal" Required="false" Visible="false"/>',
        '<Parameter Name="A" TagType="Base" DataType="BOOL" Usage="InOut" Required="true" Visible="true"/>',
        '<Parameter Name="B" TagType="Base" DataType="BOOL" Usage="InOut" Required="true" Visible="true"/>',
        '<Parameter Name="Opt_In" TagType="Base" DataType="BOOL" Usage="Input" Radix="Decimal" Required="false" Visible="true"/>',
        '<Parameter Name="Done" TagType="Base" DataType="BOOL" Usage="Output" Radix="Decimal" Required="false" Visible="true"/>',
        "</Parameters>",
        "<Routines>",
        '<Routine Name="Logic" Type="RLL">',
        "<RLLContent>",
        '<Rung Number="0" Type="N">', "<Text>", "<![CDATA[XIC(A)OTE(B);]]>", "</Text>", "</Rung>",
        "</RLLContent>",
        "</Routine>",
        "</Routines>",
        "</AddOnInstructionDefinition>",
        "</AddOnInstructionDefinitions>",
    ]
    lines += ["<Tags/>"] if tags_self_closing else ["<Tags>"] + tags + ["</Tags>"]
    lines += [
        "<Programs>",
        '<Program Name="MainProgram" TestEdits="false" MainRoutineName="Main" Disabled="false" UseAsFolder="false">',
        "<Tags>",
    ] + tag("Local_Count", "DINT", "0", '<DataValue DataType="DINT" Radix="Decimal" Value="0"/>', ' Radix="Decimal"') + [
        "</Tags>",
        "<Routines>",
        '<Routine Name="Main" Type="RLL">', "<RLLContent>", *rungs_xml(main_rungs), "</RLLContent>", "</Routine>",
        '<Routine Name="EmptyRoutine" Type="RLL">', "<RLLContent/>", "</Routine>",
        '<Routine Name="Script" Type="ST">', "<STContent>",
        '<Line Number="0">', "<![CDATA[Count := Count + 1;]]>", "</Line>",
        '<Line Number="1">', "<![CDATA[Msg := 'it''s ok';]]>", "</Line>",
        "</STContent>", "</Routine>",
        "</Routines>",
        "</Program>",
        '<Program Name="Other" TestEdits="false" MainRoutineName="Main" Disabled="false" UseAsFolder="false">',
        "<Tags/>",
        "<Routines>",
        '<Routine Name="Main" Type="RLL">', "<RLLContent>", *rungs_xml(other_rungs), "</RLLContent>", "</Routine>",
        "</Routines>",
        "</Program>",
        "</Programs>",
        "<Tasks/>",
        "</Controller>",
        "</RSLogix5000Content>",
    ]
    text = eol.join(lines) + eol
    return ("﻿" if bom else "") + text
